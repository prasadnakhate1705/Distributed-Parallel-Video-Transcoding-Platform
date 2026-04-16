import os
from dotenv import load_dotenv

load_dotenv()

AWS_REGION            = os.getenv("AWS_REGION", "us-east-1")
AWS_ACCESS_KEY_ID     = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
S3_BUCKET             = os.getenv("S3_BUCKET")          # no default — must be explicit
JOBS_TABLE            = os.getenv("JOBS_TABLE", "TranscodeJobs")

POLL_INTERVAL     = int(os.getenv("POLL_INTERVAL", "30"))
SEGMENT_DURATION  = int(os.getenv("SEGMENT_DURATION", "120"))
MAX_RETRIES       = int(os.getenv("MAX_RETRIES", "3"))
SPARK_MASTER_URL  = os.getenv("SPARK_MASTER_URL", "local[*]")


def validate() -> None:
    missing = [k for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "S3_BUCKET") if not os.getenv(k)]
    if missing:
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(missing)}\n"
            "Copy .env.example to .env and fill in the values."
        )
