import json
import re
import time
import logging
from flask import Blueprint, request, jsonify, Response, abort
from botocore.exceptions import ClientError

from api.services import s3 as s3_service
from api.services import jobs as job_service

logger = logging.getLogger(__name__)
stream_bp = Blueprint("stream", __name__)


@stream_bp.get("/videos")
def list_videos():
    keys = s3_service.list_transcoded_keys()
    return jsonify({"videos": keys})


@stream_bp.get("/stream")
def get_presigned_url():
    key = request.args.get("key")
    if not key:
        return jsonify({"error": "key param required"}), 400
    try:
        url = s3_service.presigned_url(key)
    except ClientError as exc:
        logger.exception("Could not generate presigned URL for %s", key)
        return jsonify({"error": str(exc)}), 500
    return jsonify({"url": url})


@stream_bp.get("/stream/<path:s3_key>")
def stream_video(s3_key: str):
    """Range-aware byte-range streaming from S3."""
    range_header = request.headers.get("Range")
    byte_range = None

    if range_header:
        m = re.match(r"bytes=(\d+)-(\d*)", range_header)
        if not m:
            abort(400)
        byte_range = f"bytes={m.group(1)}-{m.group(2)}"

    try:
        obj, status_code = s3_service.stream_object(s3_key, byte_range)
    except ClientError:
        abort(404)

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(obj["ContentLength"]),
    }
    if byte_range:
        headers["Content-Range"] = obj["ContentRange"]

    def _iter_chunks(body, chunk=65536):
        while True:
            data = body.read(chunk)
            if not data:
                break
            yield data

    return Response(
        _iter_chunks(obj["Body"]),
        status=status_code,
        mimetype=obj["ContentType"],
        headers=headers,
    )


@stream_bp.get("/jobs")
def list_jobs():
    status = request.args.get("status")
    items = job_service.list_jobs(status)
    return jsonify({"jobs": items})


@stream_bp.get("/jobs/<job_id>")
def get_job(job_id: str):
    item = job_service.get_job(job_id)
    if not item:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(item)


@stream_bp.get("/jobs/<job_id>/events")
def job_events(job_id: str):
    """Server-Sent Events stream for a single job.

    Emits a JSON event every 3 seconds until the job reaches a terminal state
    (COMPLETED or FAILED).  Clients that don't support SSE can still poll
    GET /jobs/<job_id> instead.
    """
    _TERMINAL = {"COMPLETED", "FAILED"}

    def _generate():
        while True:
            job = job_service.get_job(job_id)
            if not job:
                payload = json.dumps({"error": "Job not found"})
                yield f"event: error\ndata: {payload}\n\n"
                return

            # Serialise Decimal values (DurationSeconds) to float for JSON
            safe = {
                k: float(v) if hasattr(v, "__float__") and not isinstance(v, (int, str, bool)) else v
                for k, v in job.items()
            }
            yield f"data: {json.dumps(safe)}\n\n"

            if job.get("Status") in _TERMINAL:
                return

            time.sleep(3)

    return Response(
        _generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disable nginx buffering if behind a proxy
        },
    )
