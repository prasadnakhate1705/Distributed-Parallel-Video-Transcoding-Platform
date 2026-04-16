import json
import logging
import os
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_dynamo = boto3.resource("dynamodb")
_table  = _dynamo.Table(os.environ.get("JOBS_TABLE", "TranscodeJobs"))


def lambda_handler(event, context):
    logger.info("Received event: %s", json.dumps(event))
    for record in event.get("Records", []):
        key = record["s3"]["object"]["key"]
        # Guard against processing transcoded outputs that land back in the bucket
        if not key.startswith("videos/"):
            logger.info("Skipping non-input key: %s", key)
            continue
        _ensure_job(key)
    return {"status": "OK"}


def _ensure_job(input_key: str) -> None:
    """Create a minimal PENDING job only if the API hasn't already created one.

    The API uploads to S3 as  videos/{job_id}_{filename}  and writes the
    DynamoDB record keyed on that same job_id BEFORE the S3 upload.  So when
    this Lambda fires, the record already exists.  We extract the job_id from
    the key and use it as the DynamoDB primary key so the condition check is
    meaningful.

    If the key doesn't follow the expected pattern (legacy / manual upload),
    we fall back to a new uuid so the job is still created.
    """
    filename = os.path.basename(input_key)
    parts = filename.split("_", 1)

    # Expected format: {job_id}_{original_filename}
    if len(parts) == 2 and len(parts[0]) == 36:   # uuid4 is 36 chars
        job_id   = parts[0]
        name     = parts[1]
    else:
        import uuid
        job_id   = str(uuid.uuid4())
        name     = filename

    now = datetime.now(timezone.utc).isoformat()

    try:
        _table.put_item(
            Item={
                "JobId":      job_id,
                "InputKey":   input_key,
                "Name":       name,
                "Mode":       "single",
                "Renditions": [{"resolution": "1280x720", "format": "mp4", "codec": "libx264"}],
                "Status":     "PENDING",
                "CreatedAt":  now,
                "Outputs":    [],
            },
            # Only insert if the API hasn't already created a record for this job_id
            ConditionExpression="attribute_not_exists(JobId)",
        )
        logger.info("Lambda created fallback job %s for key %s", job_id, input_key)
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            logger.info("API record already exists for job %s — skipping Lambda fallback", job_id)
        else:
            raise
