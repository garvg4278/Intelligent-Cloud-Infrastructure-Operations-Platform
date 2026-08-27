# One-time, apply-locally bootstrap for Terraform's own remote state.
#
# Chicken-and-egg problem: the S3 bucket that environments/{staging,production}
# use as their backend has to exist BEFORE those configs can run `terraform
# init`, so it can't itself be created by a config that stores its state in
# that same bucket. This tiny root module is the one piece of this repo's
# Terraform that is meant to be applied with LOCAL state (a
# terraform.tfstate file on whoever runs it, or checked into a private
# location -- NOT committed to this public-shaped repo). Run it exactly
# once per AWS account/region, then never touch it again unless you're
# deliberately changing how state itself is stored.
#
# Not wired into any CI/CD or the infrastructure service on purpose --
# state-backend bootstrapping is an operator action, not something a
# platform user should be able to trigger through an API.

terraform {
  required_version = ">= 1.9.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

resource "aws_s3_bucket" "tf_state" {
  bucket = var.state_bucket_name

  # Deliberately no `force_destroy = true` -- this bucket holding every
  # environment's Terraform state is the last thing that should ever be
  # destroyed by accident.
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id
  versioning_configuration {
    status = "Enabled" # every state write is recoverable, not just the latest
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "tf_state" {
  bucket                  = aws_s3_bucket.tf_state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# State locking. Terraform >= 1.10 can lock natively against the S3 backend
# itself (`use_lockfile = true`, see environments/*/backend.tf) which is
# what this repo actually uses -- this DynamoDB table is kept anyway as the
# documented fallback for anyone applying with an older Terraform binary,
# since it costs nothing at this scale (pay-per-request) and swapping
# `use_lockfile` for `dynamodb_table` in backend.tf is a one-line change if
# you ever need it.
resource "aws_dynamodb_table" "tf_lock" {
  name         = var.lock_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }
}
