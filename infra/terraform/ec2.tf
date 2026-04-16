locals {
  # Common tags applied to both master and workers
  spark_tags = {
    Project     = var.project_name
    SparkVersion = var.spark_version
  }
}

# ── Spark Master ──────────────────────────────────────────────────────────────

resource "aws_instance" "spark_master" {
  ami                    = data.aws_ami.al2023.id
  instance_type          = var.master_instance_type
  key_name               = var.key_pair_name
  subnet_id              = data.aws_subnets.default.ids[0]
  vpc_security_group_ids = [aws_security_group.spark_cluster.id]
  iam_instance_profile   = aws_iam_instance_profile.spark_node.name

  user_data = templatefile("${path.module}/../scripts/bootstrap_master.sh", {
    spark_version         = var.spark_version
    executor_memory       = var.spark_executor_memory
    executor_cores        = var.spark_executor_cores
    s3_bucket             = aws_s3_bucket.videos.bucket
    jobs_table            = var.jobs_table_name
    aws_region            = var.aws_region
  })

  root_block_device {
    volume_size = 30
    volume_type = "gp3"
  }

  tags = merge(local.spark_tags, { Name = "${var.project_name}-spark-master", Role = "master" })
}

# ── Spark Workers ─────────────────────────────────────────────────────────────

resource "aws_instance" "spark_worker" {
  count = var.worker_count

  ami                    = data.aws_ami.al2023.id
  instance_type          = var.worker_instance_type
  key_name               = var.key_pair_name
  subnet_id              = data.aws_subnets.default.ids[0]
  vpc_security_group_ids = [aws_security_group.spark_cluster.id]
  iam_instance_profile   = aws_iam_instance_profile.spark_node.name

  user_data = templatefile("${path.module}/../scripts/bootstrap_worker.sh", {
    spark_version         = var.spark_version
    master_private_ip     = aws_instance.spark_master.private_ip
    executor_memory       = var.spark_executor_memory
    executor_cores        = var.spark_executor_cores
    s3_bucket             = aws_s3_bucket.videos.bucket
    jobs_table            = var.jobs_table_name
    aws_region            = var.aws_region
  })

  root_block_device {
    volume_size = 50    # workers need space for video segment scratch files
    volume_type = "gp3"
  }

  # Workers must start after master so they have a valid master IP to register with
  depends_on = [aws_instance.spark_master]

  tags = merge(local.spark_tags, {
    Name  = "${var.project_name}-spark-worker-${count.index + 1}"
    Role  = "worker"
    Index = count.index + 1
  })
}
