"""Single-node sequential transcoder. Reads renditions from the DynamoDB job record."""
import logging
import os
import sys
import tempfile
import time

import boto3

# Ensure repo root is on sys.path so 'from worker import ...' works when
# run via spark-submit or from an arbitrary working directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from worker import job_store, ffmpeg_utils
from worker.config import S3_BUCKET, POLL_INTERVAL, validate

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _process(job: dict) -> None:
    job_id    = job["JobId"]
    input_key = job["InputKey"]
    renditions = job.get("Renditions", [])

    if not renditions:
        raise ValueError(f"Job {job_id} has no renditions defined")

    with tempfile.TemporaryDirectory(prefix=f"transcode_{job_id}_") as work_dir:
        start = time.monotonic()

        local_in = os.path.join(work_dir, os.path.basename(input_key))
        boto3.client("s3").download_file(S3_BUCKET, input_key, local_in)
        logger.info("[%s] Downloaded input (%d renditions)", job_id, len(renditions))

        base = os.path.splitext(os.path.basename(input_key))[0]
        outputs = []

        for r in renditions:
            res   = r["resolution"]
            fmt   = r["format"]
            codec = r["codec"]
            logger.info("[%s] Transcoding rendition %s (%s, %s)", job_id, res, fmt, codec)

            # Use a per-rendition sub-directory so output files don't collide
            rend_dir = os.path.join(work_dir, res.replace("x", "_"))
            os.makedirs(rend_dir, exist_ok=True)

            # Transcode directly (no segmenting for single-node mode)
            local_out = os.path.join(rend_dir, f"{base}_{res}.{fmt}")
            ffmpeg_utils._run([
                "ffmpeg", "-y",
                "-analyzeduration", "10M", "-probesize", "20M",
                "-i", local_in,
                "-vf", f"scale={res}",
                "-c:v", codec, "-c:a", "aac",
                local_out,
            ])

            playlist = os.path.join(rend_dir, f"{base}_{res}.m3u8")
            ffmpeg_utils._run([
                "ffmpeg", "-y", "-i", local_out,
                "-c:v", "copy", "-c:a", "copy",
                "-f", "hls", "-hls_time", "10", "-hls_list_size", "0",
                "-hls_segment_filename", os.path.join(rend_dir, f"{base}_{res}_%03d.ts"),
                playlist,
            ])

            video_key, hls_key = ffmpeg_utils.upload_outputs(rend_dir, local_out, playlist, f"{base}_{res}")
            outputs.append({"resolution": res, "format": fmt, "video_key": video_key, "hls_key": hls_key})
            logger.info("[%s] Rendition %s done → %s", job_id, res, hls_key)

        duration = time.monotonic() - start
        job_store.complete(job_id, outputs, duration, "Single")
        logger.info("[%s] All %d renditions complete in %.1fs", job_id, len(outputs), duration)


def main() -> None:
    validate()
    logger.info("Single-node worker started — reading renditions from DynamoDB")
    while True:
        pending = job_store.list_pending()
        if not pending:
            logger.info("No pending jobs — sleeping %ds", POLL_INTERVAL)
            time.sleep(POLL_INTERVAL)
            continue

        for job in pending:
            if not job_store.lock(job["JobId"]):
                continue
            try:
                _process(job)
            except Exception as exc:
                logger.exception("Job %s failed", job["JobId"])
                job_store.retry_or_fail(job["JobId"], str(exc))

        time.sleep(5)


if __name__ == "__main__":
    main()
