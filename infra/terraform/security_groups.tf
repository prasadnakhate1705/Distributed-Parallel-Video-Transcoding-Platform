resource "aws_security_group" "spark_cluster" {
  name        = "${var.project_name}-spark-cluster"
  description = "Spark master/worker communication + external access"
  vpc_id      = data.aws_vpc.default.id

  # ── Inbound ──────────────────────────────────────────────────────────────

  # All traffic within the cluster (master ↔ workers, block manager, shuffle)
  ingress {
    description = "Intra-cluster"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    self        = true
  }

  # SSH — for debugging and manual spark-submit from your machine
  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ssh_cidr]
  }

  # Spark master web UI
  ingress {
    description = "Spark Master UI"
    from_port   = 8080
    to_port     = 8080
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ssh_cidr]
  }

  # Spark worker web UI
  ingress {
    description = "Spark Worker UI"
    from_port   = 8081
    to_port     = 8081
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ssh_cidr]
  }

  # spark-submit port (clients connect here to submit applications)
  ingress {
    description = "Spark Submit"
    from_port   = 7077
    to_port     = 7077
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ssh_cidr]
  }

  # SparkContext driver → executor callbacks (random high port range)
  ingress {
    description = "Spark driver callback"
    from_port   = 4040
    to_port     = 4050
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ssh_cidr]
  }

  # ── Outbound ─────────────────────────────────────────────────────────────

  # Unrestricted outbound — workers need to reach S3 and DynamoDB endpoints
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
