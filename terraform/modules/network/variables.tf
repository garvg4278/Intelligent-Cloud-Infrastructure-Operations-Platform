variable "name_prefix" {
  description = "Prefix applied to every resource name/tag in this module, e.g. \"icop-staging\"."
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.0.0.0/16"
}

variable "azs" {
  description = "Availability zones to spread subnets across. Two is the practical minimum for anything with an RDS Multi-AZ or EKS control plane in it."
  type        = list(string)
}

variable "public_subnet_cidrs" {
  description = "One CIDR per AZ, same order as var.azs. Public subnets hold the NAT gateway(s) and, if you put one there, a bastion/load balancer."
  type        = list(string)
}

variable "private_subnet_cidrs" {
  description = "One CIDR per AZ, same order as var.azs. EKS nodes, RDS, and ElastiCache all live here -- nothing in this module's private subnets gets a public IP."
  type        = list(string)
}

variable "single_nat_gateway" {
  description = "true = one shared NAT gateway for all private subnets (cheaper, single point of failure for outbound traffic -- fine for staging). false = one NAT gateway per AZ (production-grade, costs roughly one NAT gateway-hour per AZ)."
  type        = bool
  default     = true
}

variable "tags" {
  description = "Tags applied to every resource this module creates, merged with each resource's own Name tag."
  type        = map(string)
  default     = {}
}
