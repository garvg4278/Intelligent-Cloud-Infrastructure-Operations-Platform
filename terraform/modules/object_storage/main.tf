# Object storage module: one S3 bucket for the artifacts the original
# design doc describes (ROADMAP.md's linked design doc, section 7.5) --
# deployment manifests, build logs, reports, exported incident bundles,
# model artifacts. No ICOP service actually writes to S3 yet (that's a
# real gap, not hidden here -- see this module's README), but the bucket
# itself, with the security posture real object storage needs, is what
# this phase of work is about: giving the next piece of work (an
# ObjectStorageClient the deployment/analytics/aiops services could use)
# somewhere real to point at.

resource "aws_s3_bucket" "artifacts" {
  bucket        = "${var.name_prefix}-icop-artifacts"
  force_destroy = var.force_destroy
  tags          = var.tags
}

resource "aws_s3_bucket_versioning" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  versioning_configuration {
    status = var.versioning_enabled ? "Enabled" : "Disabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket                  = aws_s3_bucket.artifacts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "artifacts" {
  count  = var.lifecycle_expire_noncurrent_after_days > 0 ? 1 : 0
  bucket = aws_s3_bucket.artifacts.id

  rule {
    id     = "expire-noncurrent-versions"
    status = "Enabled"

    # AWS requires a filter block even for a rule meant to apply to every
    # object -- an empty one means "no filter, match everything."
    filter {}

    noncurrent_version_expiration {
      noncurrent_days = var.lifecycle_expire_noncurrent_after_days
    }
  }
}

# ---- SSM file-transfer bucket (Ansible connection plugin) ---------------
#
# Deliberately NOT versioned -- the amazon.aws.aws_ssm connection plugin's
# own docs flag that command output/module payloads (which can include
# whatever a task touched, secrets included, if a task isn't careful) pass
# through this bucket, so versioning would keep those around longer than
# the plugin's own auto-delete-after-run behavior intends.
resource "aws_s3_bucket" "ssm_transfer" {
  count         = var.create_ssm_transfer_bucket ? 1 : 0
  bucket        = "${var.name_prefix}-icop-ssm-transfer"
  force_destroy = true
  tags          = var.tags
}

resource "aws_s3_bucket_server_side_encryption_configuration" "ssm_transfer" {
  count  = var.create_ssm_transfer_bucket ? 1 : 0
  bucket = aws_s3_bucket.ssm_transfer[0].id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "ssm_transfer" {
  count                   = var.create_ssm_transfer_bucket ? 1 : 0
  bucket                  = aws_s3_bucket.ssm_transfer[0].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "ssm_transfer" {
  count  = var.create_ssm_transfer_bucket ? 1 : 0
  bucket = aws_s3_bucket.ssm_transfer[0].id

  rule {
    id     = "expire-everything-after-1-day"
    status = "Enabled"
    filter {}
    expiration {
      days = 1
    }
  }
}
