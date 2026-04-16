output "spark_master_public_ip" {
  description = "Public IP of the Spark master — use for SSH and spark-submit"
  value       = aws_instance.spark_master.public_ip
}

output "spark_master_url" {
  description = "Spark master URL — set as SPARK_MASTER_URL in your .env"
  value       = "spark://${aws_instance.spark_master.private_ip}:7077"
}

output "spark_master_ui" {
  description = "Spark master web UI"
  value       = "http://${aws_instance.spark_master.public_ip}:8080"
}

output "spark_worker_public_ips" {
  description = "Public IPs of all Spark workers"
  value       = aws_instance.spark_worker[*].public_ip
}

output "s3_bucket" {
  description = "S3 bucket for video uploads and outputs — set as S3_BUCKET in your .env"
  value       = aws_s3_bucket.videos.bucket
}

output "dynamodb_table" {
  description = "DynamoDB table name — set as JOBS_TABLE in your .env"
  value       = aws_dynamodb_table.jobs.name
}

output "lambda_function_name" {
  description = "Lambda function that creates job records on S3 upload"
  value       = aws_lambda_function.job_creator.function_name
}

output "ssh_master_command" {
  description = "SSH command to connect to the master node"
  value       = "ssh -i ~/.ssh/${var.key_pair_name}.pem ec2-user@${aws_instance.spark_master.public_ip}"
}

output "submit_job_command" {
  description = "Example spark-submit command to run the multi-node transcoder"
  value = join(" ", [
    "spark-submit",
    "--master spark://${aws_instance.spark_master.private_ip}:7077",
    "--executor-memory ${var.spark_executor_memory}",
    "--executor-cores ${var.spark_executor_cores}",
    "--num-executors ${var.worker_count}",
    "worker/multi_node.py"
  ])
}
