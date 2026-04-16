resource "aws_dynamodb_table" "jobs" {
  name         = var.jobs_table_name
  billing_mode = "PAY_PER_REQUEST"   # no capacity planning needed for a job queue
  hash_key     = "JobId"

  attribute {
    name = "JobId"
    type = "S"
  }

  # GSI so workers can efficiently query PENDING jobs without a full scan
  # (currently we use scan + filter; this GSI enables query-based polling)
  global_secondary_index {
    name            = "StatusIndex"
    hash_key        = "Status"
    projection_type = "ALL"
  }

  attribute {
    name = "Status"
    type = "S"
  }

  ttl {
    attribute_name = "ExpiresAt"
    enabled        = true
  }

  tags = {
    Name = var.jobs_table_name
  }
}
