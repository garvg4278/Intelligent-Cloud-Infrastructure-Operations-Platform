variable "name_prefix" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  type        = list(string)
  description = "At least 2, in different AZs -- required by aws_db_subnet_group even for a single-AZ instance."
}

variable "allowed_security_group_ids" {
  type        = list(string)
  description = "Security groups allowed to reach Postgres on 5432 -- pass modules.eks's cluster_security_group_id output so only EKS nodes (i.e. the pods every ICOP service runs as) can connect."
}

variable "instance_class" {
  type    = string
  default = "db.t4g.medium"
}

variable "allocated_storage_gb" {
  type    = number
  default = 50
}

variable "max_allocated_storage_gb" {
  type        = number
  default     = 200
  description = "Ceiling for RDS storage autoscaling. Set equal to allocated_storage_gb to disable autoscaling entirely."
}

variable "engine_version" {
  type        = string
  default     = "16.4"
  description = "Matches the postgres:16-alpine image every service's DATABASE_URL points at in docker-compose.yml -- keeping major versions aligned between local dev and real environments matters more here than chasing the newest point release."
}

variable "db_name" {
  type    = string
  default = "icop"
}

variable "master_username" {
  type    = string
  default = "icop"
}

variable "multi_az" {
  type        = bool
  default     = false
  description = "Standby replica in a second AZ with automatic failover. Real production Postgres almost always wants this true; kept false by default here since it roughly doubles RDS cost, and environments/production is what actually overrides it."
}

variable "backup_retention_days" {
  type    = number
  default = 7
}

variable "deletion_protection" {
  type    = bool
  default = false
}

variable "skip_final_snapshot" {
  type        = bool
  default     = true
  description = "true is convenient for staging (terraform destroy doesn't hang waiting on a snapshot); production should set this false so a destroy can never silently discard data."
}

variable "tags" {
  type    = map(string)
  default = {}
}
