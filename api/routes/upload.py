import uuid
import logging
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from botocore.exceptions import BotoCoreError, ClientError

from api.config import ALLOWED_EXTENSIONS
from api.services import s3 as s3_service
from api.services import jobs as job_service

logger = logging.getLogger(__name__)
upload_bp = Blueprint("upload", __name__)

_VALID_RESOLUTIONS = {"640x360", "1280x720", "1920x1080", "3840x2160"}
_VALID_CODECS      = {"libx264", "libx265", "libvpx-vp9", "libaom-av1"}
_VALID_MODES       = {"single", "parallel"}


def _allowed(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _parse_renditions(form) -> tuple[list[dict], str | None]:
    """
    Expect the form to send:
      resolutions  = one or more values (e.g. ["1280x720", "640x360"])
      format       = single value
      codec        = single value

    Returns (renditions_list, error_message_or_None).
    """
    fmt = form.get("format", "mp4")
    codec = form.get("codec", "libx264")
    resolutions = form.getlist("resolutions") or [form.get("resolution", "1280x720")]

    if fmt not in ALLOWED_EXTENSIONS:
        return [], f"Invalid format '{fmt}'. Choose from {ALLOWED_EXTENSIONS}"
    if codec not in _VALID_CODECS:
        return [], f"Invalid codec '{codec}'. Choose from {_VALID_CODECS}"

    bad = [r for r in resolutions if r not in _VALID_RESOLUTIONS]
    if bad:
        return [], f"Invalid resolution(s) {bad}. Choose from {_VALID_RESOLUTIONS}"

    renditions = [{"resolution": r, "format": fmt, "codec": codec} for r in resolutions]
    return renditions, None


@upload_bp.post("/upload")
def upload_video():
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "No file selected"}), 400
    if not _allowed(file.filename):
        return jsonify({"error": f"Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"}), 400

    mode = request.form.get("mode", "single")
    if mode not in _VALID_MODES:
        return jsonify({"error": f"Invalid mode '{mode}'. Choose 'single' or 'parallel'"}), 400

    renditions, err = _parse_renditions(request.form)
    if err:
        return jsonify({"error": err}), 400

    filename = secure_filename(file.filename)
    job_id = str(uuid.uuid4())
    s3_key = f"videos/{job_id}_{filename}"
    name = filename

    # Create the DynamoDB record BEFORE uploading to S3 so the Lambda
    # conditional-put (if it fires) won't overwrite the user's chosen renditions.
    try:
        job_service.create_job(job_id, s3_key, name, mode, renditions)
    except (BotoCoreError, ClientError) as exc:
        logger.exception("DynamoDB job creation failed for job %s", job_id)
        return jsonify({"error": str(exc)}), 500

    try:
        s3_service.upload_fileobj(file.stream, s3_key, file.mimetype)
    except (BotoCoreError, ClientError) as exc:
        logger.exception("S3 upload failed for key %s", s3_key)
        return jsonify({"error": str(exc)}), 500

    logger.info("Job %s created — %d rendition(s), mode=%s", job_id, len(renditions), mode)
    return jsonify({
        "job_id":     job_id,
        "s3_key":     s3_key,
        "renditions": renditions,
        "mode":       mode,
    }), 202
