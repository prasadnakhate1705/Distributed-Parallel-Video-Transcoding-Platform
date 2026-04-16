"""Multi-node PySpark transcoder.

Parallelism strategy: each Spark task handles one (rendition × segment) pair,
maximising cluster utilisation when a job has both multiple renditions and a
long video.  After all tasks finish, segments are merged per rendition on the
driver and the HLS playlist is packaged.
"""
import logging
import os
import sys
import tempfile
import time
from itertools import groupby

import boto3
from pyspark.sql import SparkSession

# Ensure repo root is on sys.path so 'from worker import ...' works when
# submitted via spark-submit from any working directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from worker import job_store, ffmpeg_utils
from worker.config import (
    AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY,
    S3_BUCKET, POLL_INTERVAL, SPARK_MASTER_URL, validate,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _create_spark() -> SparkSession:
    builder = (
        SparkSession.builder
        .appName("VideoTranscoder-MultiNode")
        .master(SPARK_MASTER_URL)
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
        .config("spark.serializer", "org.apache.spark.serializer.KryoSerializer")
    )

    # On EC2 with instance profiles, credentials come from the metadata service.
    # Locally (local[*]), fall back to explicit keys from env.
    if SPARK_MASTER_URL.startswith("local"):
        builder = (
            builder
            .config("spark.hadoop.fs.s3a.access.key", AWS_ACCESS_KEY_ID)
            .config("spark.hadoop.fs.s3a.secret.key", AWS_SECRET_ACCESS_KEY)
            .config("spark.executorEnv.AWS_ACCESS_KEY_ID", AWS_ACCESS_KEY_ID)
            .config("spark.executorEnv.AWS_SECRET_ACCESS_KEY", AWS_SECRET_ACCESS_KEY)
        )
    else:
        builder = builder.config(
            "spark.hadoop.fs.s3a.aws.credentials.provider",
            "com.amazonaws.auth.InstanceProfileCredentialsProvider",
        )

    return builder.getOrCreate()


def _make_transcode_task(job_id: str, s3_bucket: str):
    """Return a closure that captures only primitives — safe to pickle for Spark."""
    def _transcode_task(task):
        import tempfile, os, boto3
        from worker import ffmpeg_utils

        res, fmt, codec, seg_key = task
        # Use tempfile so we respect the executor's configured scratch space
        with tempfile.TemporaryDirectory(prefix=f"task_{job_id}_{res}_") as out_dir:
            out_key = ffmpeg_utils.transcode_segment(seg_key, out_dir, fmt, res, codec, job_id)
        return (res, fmt, out_key)

    return _transcode_task


def _process(job: dict, spark: SparkSession) -> None:
    job_id    = job["JobId"]
    input_key = job["InputKey"]
    renditions = job.get("Renditions", [])

    if not renditions:
        raise ValueError(f"Job {job_id} has no renditions defined")

    with tempfile.TemporaryDirectory(prefix=f"transcode_{job_id}_") as work_dir:
        start = time.monotonic()

        local_in = os.path.join(work_dir, os.path.basename(input_key))
        boto3.client("s3").download_file(S3_BUCKET, input_key, local_in)
        logger.info("[%s] Downloaded input", job_id)

        # Segment video once; all renditions share the same raw segments.
        segment_keys = ffmpeg_utils.segment(local_in, work_dir, job_id)
        logger.info("[%s] %d segments created", job_id, len(segment_keys))

        # Build (rendition, segment_key) task pairs — one Spark task per pair.
        tasks = [
            (r["resolution"], r["format"], r["codec"], seg_key)
            for r in renditions
            for seg_key in segment_keys
        ]

        rdd     = spark.sparkContext.parallelize(tasks, len(tasks))
        results = rdd.map(_make_transcode_task(job_id, S3_BUCKET)).collect()
        logger.info("[%s] Parallel transcode done (%d tasks)", job_id, len(results))

        # Group transcoded segment keys by rendition, then merge + HLS per rendition.
        results.sort(key=lambda x: x[0])
        outputs = []

        for res, group in groupby(results, key=lambda x: x[0]):
            group_list       = list(group)
            fmt              = group_list[0][1]
            transcoded_keys  = [g[2] for g in group_list]

            base = f"{os.path.splitext(os.path.basename(input_key))[0]}_{res}"
            merged, playlist = ffmpeg_utils.merge_and_package_hls(
                work_dir, transcoded_keys, base, fmt, res
            )
            video_key, hls_key = ffmpeg_utils.upload_outputs(work_dir, merged, playlist, base)
            outputs.append({"resolution": res, "format": fmt, "video_key": video_key, "hls_key": hls_key})
            ffmpeg_utils.cleanup_s3_segments(job_id, transcoded_keys)
            logger.info("[%s] Rendition %s packaged → %s", job_id, res, hls_key)

        duration = time.monotonic() - start
        job_store.complete(job_id, outputs, duration, "Parallel")
        logger.info("[%s] All %d renditions done in %.1fs", job_id, len(outputs), duration)


def main() -> None:
    validate()
    logger.info("Multi-node worker started — reading renditions from DynamoDB")
    spark = _create_spark()
    try:
        while True:
            pending = job_store.list_pending()
            if not pending:
                logger.info("No pending jobs — sleeping %ds", POLL_INTERVAL)
                time.sleep(POLL_INTERVAL)
                continue

            locked = [j for j in pending if job_store.lock(j["JobId"])]
            for job in locked:
                try:
                    _process(job, spark)
                except Exception as exc:
                    logger.exception("Job %s failed", job["JobId"])
                    job_store.retry_or_fail(job["JobId"], str(exc))

            time.sleep(5)
    except KeyboardInterrupt:
        logger.info("Shutting down")
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
