variable "name_prefix" {
  type        = string
  description = "e.g. \"icop-staging\" -- used as the cluster name and prefixed onto every IAM role/policy this module creates."
}

variable "cluster_version" {
  type        = string
  description = "Kubernetes minor version. Default 1.36: 1.33 left EKS standard support on 29 Jul 2026 (extended support is billed at a premium); 1.34-1.37 are in standard support. Re-check endoflife.date/amazon-eks before bumping, and upgrade one minor at a time."
  default     = "1.36"
}

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  type        = list(string)
  description = "Node group and (by default) the cluster's control-plane ENIs go here. Never public subnets -- nodes should not be directly internet-reachable."
}

variable "public_subnet_ids" {
  type        = list(string)
  description = "Only used for the cluster's public API endpoint association; nodes themselves never go here. Pass an empty list and set cluster_endpoint_public_access = false for a fully private cluster (needs a bastion or VPN to reach kubectl from)."
  default     = []
}

variable "cluster_endpoint_public_access" {
  type        = bool
  default     = true
  description = "false = kubectl (and this platform's own deployment-worker/infrastructure-worker containers, if they run outside the VPC) can only reach the API server over a VPN/Direct Connect/bastion. Real production clusters often set this false; true is the pragmatic default here since this repo has no VPN module."
}

variable "node_instance_types" {
  type    = list(string)
  default = ["t3.large"]
}

variable "node_desired_size" {
  type    = number
  default = 3
}

variable "node_min_size" {
  type    = number
  default = 2
}

variable "node_max_size" {
  type    = number
  default = 6
}

variable "node_capacity_type" {
  type        = string
  default     = "ON_DEMAND"
  description = "ON_DEMAND or SPOT. SPOT is meaningfully cheaper and fine for staging; this repo defaults every environment to ON_DEMAND and lets environments/staging override it, since a silently-interrupted staging node teaches the wrong lesson about what production will do."
}

variable "tags" {
  type    = map(string)
  default = {}
}
