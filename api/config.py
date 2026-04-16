import os
from dotenv import load_dotenv

load_dotenv()

AWS_REGION            = os.getenv("AWS_REGION", "us-east-1")
AWS_ACCESS_KEY_ID     = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
S3_BUCKET             = os.getenv("S3_BUCKET")
JOBS_TABLE            = os.getenv("JOBS_TABLE", "TranscodeJobs")
API_KEY               = os.getenv("API_KEY")

ALLOWED_EXTENSIONS   = {"mp4", "mov", "avi"}
PRESIGNED_URL_EXPIRY = 3600

_REQUIRED_KEYS = ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "S3_BUCKET", "API_KEY")


def validate() -> None:
    # Read from env at call time so tests can set vars after import
    missing = [k for k in _REQUIRED_KEYS if not os.getenv(k)]
    if missing:
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(missing)}\n"
            "Copy .env.example to .env and fill in the values."
        )
