output "bucket_name" {
  value = aws_s3_bucket.artifacts.id
}

output "bucket_arn" {
  value = aws_s3_bucket.artifacts.arn
}

output "ssm_transfer_bucket_name" {
  description = "Pass this to ansible/inventory as ansible_aws_ssm_bucket_name. Empty string if create_ssm_transfer_bucket = false."
  value       = var.create_ssm_transfer_bucket ? aws_s3_bucket.ssm_transfer[0].id : ""
}
