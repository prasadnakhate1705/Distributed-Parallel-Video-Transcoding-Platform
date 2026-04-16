import boto3
from api.config import (
    AWS_REGION, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY,
    S3_BUCKET, PRESIGNED_URL_EXPIRY,
)

_s3 = boto3.client(
    "s3",
    region_name=AWS_REGION,
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
)


def upload_fileobj(fileobj, key: str, content_type: str) -> None:
    _s3.upload_fileobj(
        Fileobj=fileobj,
        Bucket=S3_BUCKET,
        Key=key,
        ExtraArgs={"ContentType": content_type},
    )


def list_transcoded_keys(prefix: str = "transcoded/") -> list[str]:
    resp = _s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=prefix)
    return [obj["Key"] for obj in resp.get("Contents", [])]


def presigned_url(key: str) -> str:
    return _s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": S3_BUCKET, "Key": key},
        ExpiresIn=PRESIGNED_URL_EXPIRY,
    )


def stream_object(key: str, byte_range: str | None = None):
    """Return (boto3 response dict, status_code).  Supports Range requests."""
    kwargs = {"Bucket": S3_BUCKET, "Key": key}
    if byte_range:
        kwargs["Range"] = byte_range
    obj = _s3.get_object(**kwargs)
    status = 206 if byte_range else 200
    return obj, status
