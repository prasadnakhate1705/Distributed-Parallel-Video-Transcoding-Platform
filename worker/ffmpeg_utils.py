"""FFmpeg helpers: segment, transcode, merge, HLS packaging."""
import logging
import os
import subprocess

import boto3
from botocore.exceptions import ClientError

from worker.config import S3_BUCKET, SEGMENT_DURATION

logger = logging.getLogger(__name__)

# Module-level singleton — avoid creating a new client per call
_s3_client = boto3.client("s3")


def segment(input_file: str, work_dir: str, job_id: str) -> list[str]:
    """Split input_file into SEGMENT_DURATION-second .ts chunks and upload to S3."""
    pattern = os.path.join(work_dir, "segment%03d.ts")
    cmd = [
        "ffmpeg", "-y", "-i", input_file,
        "-c", "copy",
        "-segment_time", str(SEGMENT_DURATION),
        "-f", "segment",
        "-reset_timestamps", "1",
        pattern,
    ]
    _run(cmd)

    files = sorted(f for f in os.listdir(work_dir) if f.startswith("segment") and f.endswith(".ts"))
    if not files:
        raise RuntimeError("FFmpeg produced no segments — check input file")

    prefix = f"transcoded/segments/{job_id}/"
    keys = []
    for name in files:
        key = prefix + name
        _s3_client.upload_file(os.path.join(work_dir, name), S3_BUCKET, key)
        keys.append(key)
        logger.info("Uploaded segment %s", key)
    return keys


def transcode_segment(s3_key: str, work_dir: str, fmt: str, resolution: str, codec: str, job_id: str) -> str:
    """Download one segment from S3, transcode it, re-upload, return output S3 key."""
    os.makedirs(work_dir, exist_ok=True)

    name = os.path.basename(s3_key)
    local_in  = os.path.join(work_dir, name)
    local_out = os.path.join(work_dir, f"out_{name}")

    try:
        _s3_client.download_file(S3_BUCKET, s3_key, local_in)
    except ClientError as exc:
        raise RuntimeError(f"Download failed for {s3_key}: {exc}") from exc

    cmd = [
        "ffmpeg", "-y",
        "-analyzeduration", "10M", "-probesize", "20M",
        "-i", local_in,
        "-vf", f"scale={resolution}",
        "-c:v", codec, "-c:a", "aac",
        "-f", "mpegts",
        local_out,
    ]
    _run(cmd)

    # Namespace by job_id + resolution to prevent concurrent-job key collisions
    safe_res = resolution.replace("x", "_")
    out_key = f"transcoded/segments/{job_id}/{safe_res}/out_{name}"
    _s3_client.upload_file(local_out, S3_BUCKET, out_key)
    return out_key


def merge_and_package_hls(
    work_dir: str, transcoded_keys: list[str], base_name: str, fmt: str, resolution: str
) -> tuple[str, str]:
    """Download transcoded segments, concatenate, create HLS. Returns (video_path, m3u8_path)."""
    for key in transcoded_keys:
        _s3_client.download_file(S3_BUCKET, key, os.path.join(work_dir, os.path.basename(key)))

    segments = sorted(f for f in os.listdir(work_dir) if f.startswith("out_") and f.endswith(".ts"))
    list_file = os.path.join(work_dir, "concat.txt")
    with open(list_file, "w") as fh:
        for seg in segments:
            # Use absolute paths so FFmpeg concat works regardless of CWD
            fh.write(f"file '{os.path.join(work_dir, seg)}'\n")

    merged = os.path.join(work_dir, f"{base_name}_{resolution}.{fmt}")
    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file, "-c", "copy", merged])

    playlist = os.path.join(work_dir, f"{base_name}.m3u8")
    _run([
        "ffmpeg", "-y", "-i", merged,
        "-c:v", "copy", "-c:a", "copy",
        "-f", "hls", "-hls_time", "10", "-hls_list_size", "0",
        "-hls_segment_filename", os.path.join(work_dir, f"{base_name}_%03d.ts"),
        playlist,
    ])

    return merged, playlist


def upload_outputs(work_dir: str, merged: str, playlist: str, base_name: str) -> tuple[str, str]:
    """Upload final video + all HLS files to S3. Returns (video_key, playlist_key)."""
    prefix = "transcoded/"

    video_key = prefix + os.path.basename(merged)
    _s3_client.upload_file(merged, S3_BUCKET, video_key)

    playlist_key = prefix + os.path.basename(playlist)
    for fname in os.listdir(work_dir):
        if fname.startswith(base_name) and (fname.endswith(".m3u8") or fname.endswith(".ts")):
            _s3_client.upload_file(os.path.join(work_dir, fname), S3_BUCKET, prefix + fname)

    return video_key, playlist_key


def cleanup_s3_segments(job_id: str, transcoded_keys: list[str]) -> None:
    to_delete = []

    resp = _s3_client.list_objects_v2(Bucket=S3_BUCKET, Prefix=f"transcoded/segments/{job_id}/")
    to_delete += [{"Key": o["Key"]} for o in resp.get("Contents", []) if o["Key"].endswith(".ts")]
    to_delete += [{"Key": k} for k in transcoded_keys if k.endswith(".ts")]

    if to_delete:
        _s3_client.delete_objects(Bucket=S3_BUCKET, Delete={"Objects": to_delete})
        logger.info("Deleted %d intermediate segments for job %s", len(to_delete), job_id)


def _run(cmd: list[str]) -> None:
    logger.debug("Running: %s", " ".join(cmd))
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode(errors="replace") if exc.stderr else ""
        logger.error("FFmpeg failed (exit %d):\n%s", exc.returncode, stderr)
        raise RuntimeError(f"FFmpeg exited {exc.returncode}: {stderr[-500:]}") from exc
