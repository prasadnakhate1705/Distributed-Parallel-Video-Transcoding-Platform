#!/bin/bash
# Bootstrap script for the Spark master node.
# Runs as root via EC2 user-data on first boot.
# Terraform injects template variables (${spark_version}, etc.) before upload.
set -euo pipefail
exec > >(tee /var/log/spark-bootstrap.log | logger -t spark-bootstrap) 2>&1

echo "=== Starting Spark master bootstrap ==="

# ── System packages ───────────────────────────────────────────────────────────
dnf update -y
dnf install -y java-11-amazon-corretto-headless python3 python3-pip wget tar

# FFmpeg via a third-party repo (not in AL2023 main)
dnf install -y https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm || true
dnf install -y ffmpeg ffmpeg-devel || {
  # Fallback: compile a static build
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
SPARK_URL="https://downloads.apache.org/spark/spark-$${SPARK_VERSION}/$${SPARK_TGZ}"

wget -q "$${SPARK_URL}" -O /tmp/$${SPARK_TGZ}
tar -xzf /tmp/$${SPARK_TGZ} -C /opt/
ln -sfn /opt/spark-$${SPARK_VERSION}-bin-hadoop3 $${SPARK_HOME}
rm /tmp/$${SPARK_TGZ}
echo "Spark $${SPARK_VERSION} installed at $${SPARK_HOME}"

# ── Environment ───────────────────────────────────────────────────────────────
JAVA_HOME=$(dirname $(dirname $(readlink -f $(which java))))
export SPARK_HOME JAVA_HOME
export PATH="$${PATH}:$${SPARK_HOME}/bin:$${SPARK_HOME}/sbin"
export S3_BUCKET="${s3_bucket}"
export JOBS_TABLE="${jobs_table}"
export AWS_REGION="${aws_region}"

# Also persist for future login sessions
cat >> /etc/environment << EOF
SPARK_HOME=$${SPARK_HOME}
JAVA_HOME=$${JAVA_HOME}
PATH=$${PATH}
S3_BUCKET=${s3_bucket}
JOBS_TABLE=${jobs_table}
AWS_REGION=${aws_region}
EOF

# ── Spark configuration ───────────────────────────────────────────────────────
MASTER_PRIVATE_IP=$(curl -s http://169.254.169.254/latest/meta-data/local-ipv4)

cat > $${SPARK_HOME}/conf/spark-env.sh << EOF
export JAVA_HOME=$(dirname $(dirname $(readlink -f $(which java))))
export SPARK_MASTER_HOST=$${MASTER_PRIVATE_IP}
export SPARK_MASTER_PORT=7077
export SPARK_MASTER_WEBUI_PORT=8080
export SPARK_WORKER_MEMORY=${executor_memory}
export SPARK_WORKER_CORES=${executor_cores}
export SPARK_LOG_DIR=/var/log/spark
export SPARK_PID_DIR=/var/run/spark
# Pass AWS credentials via instance profile — no keys in config files
EOF

cat > $${SPARK_HOME}/conf/spark-defaults.conf << EOF
spark.eventLog.enabled                    false
spark.serializer                          org.apache.spark.serializer.KryoSerializer
spark.hadoop.fs.s3a.aws.credentials.provider  com.amazonaws.auth.InstanceProfileCredentialsProvider
spark.hadoop.fs.s3a.impl                  org.apache.hadoop.fs.s3a.S3AFileSystem
EOF

mkdir -p /var/log/spark /var/run/spark
chown ec2-user:ec2-user /var/log/spark /var/run/spark

# ── Python dependencies ───────────────────────────────────────────────────────
pip3 install boto3 pyspark==${spark_version} python-dotenv psutil

# ── Start Spark master ────────────────────────────────────────────────────────
sudo -u ec2-user $${SPARK_HOME}/sbin/start-master.sh

# Write master URL to a well-known file so workers and scripts can read it
echo "spark://$${MASTER_PRIVATE_IP}:7077" > /home/ec2-user/spark-master-url.txt
chown ec2-user:ec2-user /home/ec2-user/spark-master-url.txt

echo "=== Spark master bootstrap complete ==="
echo "Master URL: spark://$${MASTER_PRIVATE_IP}:7077"
echo "Master UI:  http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4):8080"
