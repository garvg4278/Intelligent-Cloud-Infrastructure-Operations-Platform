output "cluster_name" {
  value = module.eks.cluster_name
}

output "configure_kubectl" {
  value = module.eks.configure_kubectl
}

output "db_endpoint" {
  value = module.rds.db_endpoint
}

output "db_secret_arn" {
  value = module.rds.secret_arn
}

output "redis_endpoint" {
  value = module.elasticache.redis_endpoint
}

output "artifacts_bucket" {
  value = module.object_storage.bucket_name
}

output "deployment_irsa_role_arn" {
  value = module.deployment_irsa.role_arn
}

output "vpc_id" {
  value = module.network.vpc_id
}

output "ssm_transfer_bucket" {
  description = "Pass to ../../../ansible/inventory as ansible_aws_ssm_bucket_name."
  value       = module.object_storage.ssm_transfer_bucket_name
}
