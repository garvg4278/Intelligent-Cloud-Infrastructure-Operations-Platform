variable "name_prefix" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "allowed_security_group_ids" {
  type        = list(string)
  description = "Pass modules.eks's cluster_security_group_id output -- only EKS nodes reach Redis on 6379."
}

variable "node_type" {
  type    = string
  default = "cache.t4g.small"
}

variable "engine_version" {
  type        = string
  default     = "7.1"
  description = "Matches docker-compose.yml's redis:7-alpine major version."
}

variable "num_cache_nodes" {
  type        = number
  default     = 1
  description = "1 = single node, no replica (matches docker-compose's single redis container -- fine for staging). 2+ = primary plus read replica(s) with automatic failover; environments/production overrides this. ElastiCache calls the whole group's node count this even though it provisions it as a replication group under the hood -- see automatic_failover_enabled below."
}

variable "tags" {
  type    = map(string)
  default = {}
}
