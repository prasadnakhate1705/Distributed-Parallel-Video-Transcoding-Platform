from datetime import datetime, timezone, timedelta

import boto3
from boto3.dynamodb.conditions import Attr
from api.config import (
    AWS_REGION, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, JOBS_TABLE,
)

_dynamo = boto3.resource(
    "dynamodb",
    region_name=AWS_REGION,
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
)
_table = _dynamo.Table(JOBS_TABLE)

_JOB_TTL_DAYS = 30


def create_job(
    job_id: str,
    input_key: str,
    name: str,
    mode: str,
    renditions: list[dict],
) -> None:
    """Write a full job record to DynamoDB before the S3 upload fires Lambda."""
    now     = datetime.now(timezone.utc)
    expires = int((now + timedelta(days=_JOB_TTL_DAYS)).timestamp())

    _table.put_item(Item={
        "JobId":      job_id,
        "InputKey":   input_key,
        "Name":       name,
        "Mode":       mode,
        "Renditions": renditions,
        "Status":     "PENDING",
        "CreatedAt":  now.isoformat(),
        "Outputs":    [],
        "ExpiresAt":  expires,   # DynamoDB TTL — auto-deletes record after 30 days
    })


def get_job(job_id: str) -> dict | None:
    resp = _table.get_item(Key={"JobId": job_id})
    return resp.get("Item")


def list_jobs(status: str | None = None) -> list[dict]:
    """Return all jobs, handling DynamoDB 1 MB pagination."""
    items  = []
    kwargs = {}
    if status:
        kwargs["FilterExpression"] = Attr("Status").eq(status)

    while True:
        resp = _table.scan(**kwargs)
        items.extend(resp.get("Items", []))
        last = resp.get("LastEvaluatedKey")
        if not last:
            break
        kwargs["ExclusiveStartKey"] = last

    return items
