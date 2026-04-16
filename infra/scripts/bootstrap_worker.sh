#!/bin/bash
# Bootstrap script for Spark worker nodes.
# Terraform injects ${master_private_ip} and other vars before upload.
set -euo pipefail
exec > >(tee /var/log/spark-bootstrap.log | logger -t spark-bootstrap) 2>&1

echo "=== Starting Spark worker bootstrap ==="
echo "Registering with master at ${master_private_ip}:7077"

# ── System packages ───────────────────────────────────────────────────────────
dnf update -y
dnf install -y java-11-amazon-corretto-headless python3 python3-pip wget tar

# FFmpeg
dnf install -y https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm || true
dnf install -y ffmpeg ffmpeg-devel || {
  wget -q https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz
  tar -xf ffmpeg-release-amd64-static.tar.xz
  mv ffmpeg-*-static/ffmpeg ffmpeg-*-static/ffprobe /usr/local/bin/
  rm -rf ffmpeg-*
}
echo "FFmpeg: $(ffmpeg -version 2>&1 | head -1)"

# ── Spark installation ────────────────────────────────────────────────────────
SPARK_VERSION="${spark_version}"
SPARK_HOME="/opt/spark"
SPARK_TGZ="spark-$${SPARK_VERSION}-bin-hadoop3.tgz"

wget -q "https://downloads.apache.org/spark/spark-$${SPARK_VERSION}/$${SPARK_TGZ}" -O /tmp/$${SPARK_TGZ}
tar -xzf /tmp/$${SPARK_TGZ} -C /opt/
ln -sfn /opt/spark-$${SPARK_VERSION}-bin-hadoop3 $${SPARK_HOME}
rm /tmp/$${SPARK_TGZ}

# ── Environment ───────────────────────────────────────────────────────────────
JAVA_HOME=$(dirname $(dirname $(readlink -f $(which java))))
export SPARK_HOME JAVA_HOME
export PATH="$${PATH}:$${SPARK_HOME}/bin:$${SPARK_HOME}/sbin"
export S3_BUCKET="${s3_bucket}"
export JOBS_TABLE="${jobs_table}"
export AWS_REGION="${aws_region}"

cat >> /etc/environment << EOF
SPARK_HOME=$${SPARK_HOME}
JAVA_HOME=$${JAVA_HOME}
PATH=$${PATH}
S3_BUCKET=${s3_bucket}
JOBS_TABLE=${jobs_table}
AWS_REGION=${aws_region}
EOF

# ── Spark configuration ───────────────────────────────────────────────────────
WORKER_PRIVATE_IP=$(curl -s http://169.254.169.254/latest/meta-data/local-ipv4)

cat > $${SPARK_HOME}/conf/spark-env.sh << EOF
export JAVA_HOME=$(dirname $(dirname $(readlink -f $(which java))))
export SPARK_WORKER_HOST=$${WORKER_PRIVATE_IP}
export SPARK_WORKER_WEBUI_PORT=8081
export SPARK_WORKER_MEMORY=${executor_memory}
export SPARK_WORKER_CORES=${executor_cores}
export SPARK_LOG_DIR=/var/log/spark
export SPARK_PID_DIR=/var/run/spark
EOF

mkdir -p /var/log/spark /var/run/spark
chown ec2-user:ec2-user /var/log/spark /var/run/spark

# ── Python dependencies ───────────────────────────────────────────────────────
pip3 install boto3 pyspark==${spark_version} python-dotenv psutil

# ── Start Spark worker ────────────────────────────────────────────────────────
# Retry loop — master may not be fully up when worker starts
MASTER_URL="spark://${master_private_ip}:7077"
MAX_WAIT=120
WAITED=0
until nc -z ${master_private_ip} 7077 || [ $WAITED -ge $MAX_WAIT ]; do
  echo "Waiting for master at ${master_private_ip}:7077 ($${WAITED}s)..."
  sleep 5
  WAITED=$((WAITED + 5))
done

if [ $WAITED -ge $MAX_WAIT ]; then
  echo "ERROR: Master never became available after $${MAX_WAIT}s"
  exit 1
fi

sudo -u ec2-user $${SPARK_HOME}/sbin/start-worker.sh $${MASTER_URL}
echo "=== Spark worker bootstrap complete — registered with $${MASTER_URL} ==="
