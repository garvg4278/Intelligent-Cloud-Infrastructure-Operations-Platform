# Remote state for the staging environment. The bucket referenced here has
# to already exist -- see terraform/bootstrap, applied once, separately,
# before this file's `terraform init` can succeed.
#
# `use_lockfile = true` is native S3 state locking (Terraform >= 1.10,
# see the CHANGELOG -- no DynamoDB table required, one less moving part
# than the classic dynamodb_table approach). If you're on an older
# Terraform binary, delete that line and add:
#   dynamodb_table = "icop-terraform-locks"
# (the table terraform/bootstrap also creates, for exactly this fallback).
terraform {
  backend "s3" {
    bucket       = "icop-terraform-state-CHANGE-ME" # must match terraform/bootstrap's state_bucket_name
    key          = "icop/staging/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}
