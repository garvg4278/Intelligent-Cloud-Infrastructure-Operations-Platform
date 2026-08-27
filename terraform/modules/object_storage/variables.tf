variable "name_prefix" {
  type = string
}

variable "versioning_enabled" {
  type    = bool
  default = true
}

variable "force_destroy" {
  type        = bool
  description = "true lets `terraform destroy` delete the bucket even if it still has objects in it -- convenient for staging, dangerous for production (environments/production leaves this false)."
  default     = false
}

variable "lifecycle_expire_noncurrent_after_days" {
  type        = number
  default     = 90
  description = "Old versions of an object (from versioning_enabled) older than this are deleted automatically, so this bucket doesn't grow forever. 0 disables the rule."
}

variable "create_ssm_transfer_bucket" {
  type        = bool
  default     = true
  description = "Ansible's amazon.aws.aws_ssm connection plugin (../../../ansible/) needs an S3 bucket to relay files/module code through when it talks to a node over Session Manager -- see ../../../ansible/README.md for why SSM instead of SSH. Separate from the artifacts bucket above on purpose: this one holds only transient, auto-expiring transfer files, never anything a person would want versioned or kept."
}

variable "tags" {
  type    = map(string)
  default = {}
}
