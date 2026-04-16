"""All DynamoDB operations for the worker. Single source of truth."""
import logging
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

from worker.config import AWS_REGION, JOBS_TABLE, MAX_RETRIES

logger = logging.getLogger(__name__)

_dynamo = boto3.resource("dynamodb", region_name=AWS_REGION)
_table  = _dynamo.Table(JOBS_TABLE)


def list_pending() -> list[dict]:
    """Return all PENDING jobs, handling DynamoDB pagination."""
    items = []
    kwargs = {
        "FilterExpression": "#s = :p",
        "ExpressionAttributeNames": {"#s": "Status"},
        "ExpressionAttributeValues": {":p": "PENDING"},
    }
    try:
        while True:
            resp = _table.scan(**kwargs)
            items.extend(resp.get("Items", []))
            last = resp.get("LastEvaluatedKey")
            if not last:
                break
            kwargs["ExclusiveStartKey"] = last
    except ClientError:
        logger.exception("Failed to scan for pending jobs")
    return items


def lock(job_id: str) -> bool:
    """Atomically move PENDING → PROCESSING. Returns False if already claimed."""
    try:
        _table.update_item(
            Key={"JobId": job_id},
            ConditionExpression="#s = :pending",
            UpdateExpression="SET #s = :processing",
            ExpressionAttributeNames={"#s": "Status"},
            ExpressionAttributeValues={":pending": "PENDING", ":processing": "PROCESSING"},
        )
        return True
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        logger.exception("Unexpected error locking job %s", job_id)
        return False


def complete(job_id: str, outputs: list[dict], duration: float, mode: str) -> None:
    """
    Mark a job COMPLETED with all rendition outputs.

    outputs format:
      [{"resolution": "1280x720", "format": "mp4",
        "video_key": "transcoded/...", "hls_key": "transcoded/....m3u8"}, ...]
    """
    try:
        _table.update_item(
            Key={"JobId": job_id},
            UpdateExpression=(
                "SET #s = :s, Outputs = :o, DurationSeconds = :d, "
                "#m = :m, CompletedAt = :t"
            ),
            ExpressionAttributeNames={"#s": "Status", "#m": "Mode"},
            ExpressionAttributeValues={
                ":s": "COMPLETED",
                ":o": outputs,
                ":d": Decimal(str(round(duration, 3))),
                ":m": mode,
                ":t": datetime.now(timezone.utc).isoformat(),
            },
        )
    except ClientError:
        logger.exception("Failed to mark job %s COMPLETED", job_id)


def retry_or_fail(job_id: str, error: str) -> None:
    """On worker failure: re-queue the job if retries remain, else mark FAILED.

    A single atomic UpdateExpression increments RetryCount and sets the new
    Status in one call, eliminating the race window between two separate updates.
    """
    # Determine new status based on whether retries remain.
    # We first read current RetryCount, then do one atomic update.
    try:
        item = _table.get_item(Key={"JobId": job_id}).get("Item", {})
        current_retries = int(item.get("RetryCount", 0))
        new_retries     = current_retries + 1
        new_status      = "PENDING" if new_retries <= MAX_RETRIES else "FAILED"

        _table.update_item(
            Key={"JobId": job_id},
            ConditionExpression="#s = :processing",
            UpdateExpression="SET #s = :ns, RetryCount = :rc, LastError = :e",
            ExpressionAttributeNames={"#s": "Status"},
            ExpressionAttributeValues={
                ":processing": "PROCESSING",
                ":ns":         new_status,
                ":rc":         new_retries,
                ":e":          error,
            },
        )

        if new_status == "PENDING":
            logger.warning("Job %s re-queued (attempt %d/%d): %s", job_id, new_retries, MAX_RETRIES, error)
        else:
            logger.error("Job %s permanently failed after %d attempts: %s", job_id, new_retries, error)

    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            logger.warning("Job %s was not in PROCESSING state during retry_or_fail — skipping", job_id)
        else:
            logger.exception("Error in retry_or_fail for job %s", job_id)
