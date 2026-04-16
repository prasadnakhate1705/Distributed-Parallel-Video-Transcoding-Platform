#!/bin/bash
# Submit the multi-node transcoding job to the Spark standalone cluster.
# Run this from the repo root after `terraform apply`.
#
# Usage:
#   ./infra/scripts/submit_job.sh
#
# Reads SPARK_MASTER_URL from .env or environment.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

# Load .env if present
if [ -f "$REPO_ROOT/.env" ]; then
  set -o allexport
  source "$REPO_ROOT/.env"
  set +o allexport
fi

: "${SPARK_MASTER_URL:?SPARK_MASTER_URL is not set. Run terraform output spark_master_url}"
: "${S3_BUCKET:?S3_BUCKET is not set}"
: "${JOBS_TABLE:?JOBS_TABLE is not set}"
: "${AWS_REGION:?AWS_REGION is not set}"

WORKER_COUNT="${WORKER_COUNT:-2}"
EXECUTOR_MEMORY="${EXECUTOR_MEMORY:-2g}"
EXECUTOR_CORES="${EXECUTOR_CORES:-2}"

echo "Submitting to:  $SPARK_MASTER_URL"
echo "Workers:        $WORKER_COUNT"
echo "Executor memory: $EXECUTOR_MEMORY / cores: $EXECUTOR_CORES"

spark-submit \
  --master "$SPARK_MASTER_URL" \
  --executor-memory "$EXECUTOR_MEMORY" \
  --executor-cores  "$EXECUTOR_CORES" \
  --num-executors   "$WORKER_COUNT" \
  --conf "spark.hadoop.fs.s3a.aws.credentials.provider=com.amazonaws.auth.InstanceProfileCredentialsProvider" \
  --conf "spark.hadoop.fs.s3a.impl=org.apache.hadoop.fs.s3a.S3AFileSystem" \
  --conf "spark.serializer=org.apache.spark.serializer.KryoSerializer" \
  --conf "spark.executor.extraJavaOptions=-XX:+UseG1GC" \
  "$REPO_ROOT/worker/multi_node.py"
