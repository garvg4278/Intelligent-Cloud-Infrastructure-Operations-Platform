variable "aws_region" {
  description = "Region the state bucket and lock table live in. Every environment's backend.tf must point at this same region."
  type        = string
  default     = "us-east-1"
}

variable "state_bucket_name" {
  description = "Globally-unique S3 bucket name for Terraform remote state. S3 bucket names are global across all of AWS, not just your account -- the default below WILL collide with someone else's; change it before applying."
  type        = string
  default     = "icop-terraform-state-CHANGE-ME"
}

variable "lock_table_name" {
  description = "DynamoDB table used for state locking on Terraform < 1.10, or as a documented fallback. Not read by backend.tf's default (native S3 locking) configuration."
  type        = string
  default     = "icop-terraform-locks"
}
