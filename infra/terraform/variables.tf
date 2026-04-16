variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Prefix for all resource names"
  type        = string
  default     = "videotranscoder"
}

variable "key_pair_name" {
  description = "Name of an existing EC2 key pair for SSH access"
  type        = string
}

variable "allowed_ssh_cidr" {
  description = "CIDR allowed to SSH into the cluster. Use your IP: x.x.x.x/32. No default — must be set explicitly to avoid exposing the cluster."
  type        = string

  validation {
    condition     = can(cidrhost(var.allowed_ssh_cidr, 0))
    error_message = "allowed_ssh_cidr must be a valid CIDR block (e.g. 203.0.113.10/32)."
  }
}

variable "master_instance_type" {
  description = "EC2 instance type for the Spark master"
  type        = string
  default     = "t3.medium"
}

variable "worker_instance_type" {
  description = "EC2 instance type for each Spark worker"
  type        = string
  default     = "t3.large"
}

variable "worker_count" {
  description = "Number of Spark worker nodes"
  type        = number
  default     = 2
}

variable "spark_version" {
  description = "Apache Spark version to install"
  type        = string
  default     = "3.5.1"
}

variable "spark_executor_memory" {
  description = "Memory allocated per Spark executor"
  type        = string
  default     = "2g"
}

variable "spark_executor_cores" {
  description = "CPU cores allocated per Spark executor"
  type        = number
  default     = 2
}

variable "jobs_table_name" {
  description = "DynamoDB table name for transcoding jobs"
  type        = string
  default     = "TranscodeJobs"
}
