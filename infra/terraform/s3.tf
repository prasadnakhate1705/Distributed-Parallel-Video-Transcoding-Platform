resource "aws_s3_bucket" "videos" {
  bucket = "${var.project_name}-videos-${data.aws_caller_identity.current.account_id}"

  lifecycle {
    prevent_destroy = false  # set true in production
  }
}

resource "aws_s3_bucket_versioning" "videos" {
  bucket = aws_s3_bucket.videos.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "videos" {
  bucket = aws_s3_bucket.videos.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "videos" {
  bucket                  = aws_s3_bucket.videos.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# S3 → Lambda trigger (fires on every object created under videos/)
resource "aws_s3_bucket_notification" "upload_trigger" {
  bucket = aws_s3_bucket.videos.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.job_creator.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "videos/"
  }

  depends_on = [aws_lambda_permission.allow_s3]
}

data "aws_caller_identity" "current" {}
