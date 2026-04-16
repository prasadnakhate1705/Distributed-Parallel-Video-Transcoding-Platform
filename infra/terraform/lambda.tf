# Package the Lambda handler from the lambda/ directory
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_file = "${path.module}/../../lambda/handler.py"
  output_path = "${path.module}/.build/lambda_handler.zip"
}

resource "aws_lambda_function" "job_creator" {
  function_name    = "${var.project_name}-job-creator"
  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  role             = aws_iam_role.lambda_exec.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  timeout          = 30

  environment {
    variables = {
      JOBS_TABLE = var.jobs_table_name
    }
  }
}

# Allow S3 to invoke the Lambda
resource "aws_lambda_permission" "allow_s3" {
  statement_id  = "AllowS3Invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.job_creator.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.videos.arn
}

resource "aws_cloudwatch_log_group" "lambda_logs" {
  name              = "/aws/lambda/${aws_lambda_function.job_creator.function_name}"
  retention_in_days = 7
}
