output "cluster_name" {
  value = aws_eks_cluster.this.name
}

output "cluster_endpoint" {
  value = aws_eks_cluster.this.endpoint
}

output "cluster_certificate_authority_data" {
  value = aws_eks_cluster.this.certificate_authority[0].data
}

output "cluster_security_group_id" {
  description = "The SG EKS creates automatically for the control plane <-> node communication -- this is the one to reference from the RDS/ElastiCache modules' security group rules (allow-from-this-SG), not modules.eks's own aws_security_group.cluster (which is an empty placeholder, see main.tf)."
  value       = aws_eks_cluster.this.vpc_config[0].cluster_security_group_id
}

output "oidc_provider_arn" {
  value = aws_iam_openid_connect_provider.eks.arn
}

output "oidc_provider_url" {
  value = replace(aws_iam_openid_connect_provider.eks.url, "https://", "")
}

output "node_role_arn" {
  value = aws_iam_role.node.arn
}

output "configure_kubectl" {
  description = "Copy-paste command to point kubectl at this cluster once it exists."
  value       = "aws eks update-kubeconfig --name ${aws_eks_cluster.this.name} --region <your-region>"
}
