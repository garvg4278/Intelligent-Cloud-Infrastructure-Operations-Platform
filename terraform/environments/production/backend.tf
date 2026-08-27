terraform {
  backend "s3" {
    bucket       = "icop-terraform-state-CHANGE-ME" # same bucket as staging (terraform/bootstrap), different key
    key          = "icop/production/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}
