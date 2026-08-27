output "role_arn" {
  description = "Annotate the matching Kubernetes ServiceAccount with eks.amazonaws.com/role-arn: <this> (the GitOps Helm chart -- infra/helm/service-chart -- would need a serviceAccount.annotations value added to actually set this; not yet present in that chart, see this module's README)."
  value       = aws_iam_role.this.arn
}
