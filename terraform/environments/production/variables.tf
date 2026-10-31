variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "azs" {
  type        = list(string)
  description = "Three AZs in production -- EKS itself only requires two, but a three-way spread keeps RDS Multi-AZ and the NAT-per-AZ topology from concentrating around a single AZ failure."
  default     = ["us-east-1a", "us-east-1b", "us-east-1c"]
}

variable "vpc_cidr" {
  type    = string
  default = "10.20.0.0/16"
}

variable "public_subnet_cidrs" {
  type    = list(string)
  default = ["10.20.0.0/24", "10.20.1.0/24", "10.20.2.0/24"]
}

variable "private_subnet_cidrs" {
  type    = list(string)
  default = ["10.20.10.0/24", "10.20.11.0/24", "10.20.12.0/24"]
}

variable "eks_cluster_version" {
  type    = string
  default     = "1.36"
}

variable "node_instance_types" {
  type    = list(string)
  default = ["m6i.large"]
}

variable "node_desired_size" {
  type    = number
  default = 4
}

variable "node_max_size" {
  type    = number
  default = 10
}

variable "db_instance_class" {
  type    = string
  default = "db.r6g.large"
}

variable "redis_node_type" {
  type    = string
  default = "cache.r6g.large"
}
