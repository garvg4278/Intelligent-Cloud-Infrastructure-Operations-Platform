variable "role_name" {
  type        = string
  description = "e.g. \"icop-staging-deployment-artifacts\""
}

variable "oidc_provider_arn" {
  type        = string
  description = "modules.eks's oidc_provider_arn output."
}

variable "oidc_provider_url" {
  type        = string
  description = "modules.eks's oidc_provider_url output (no https:// prefix)."
}

variable "namespace" {
  type        = string
  description = "Kubernetes namespace the service account lives in, e.g. \"icop-staging\"."
}

variable "service_account_name" {
  type        = string
  description = "Kubernetes ServiceAccount name this role trusts, e.g. \"deployment\". Must match the ServiceAccount the GitOps chart actually creates and the pod actually runs as -- IRSA's whole security model is this exact-match binding, see this module's README."
}

variable "policy_json" {
  type        = string
  description = "IAM policy document (as JSON, typically from a data \"aws_iam_policy_document\" block in the caller) granting exactly what this service account needs -- e.g. s3:GetObject/PutObject scoped to one bucket ARN. This module does not supply a default policy on purpose: least-privilege means every caller states its own, see ROADMAP.md's linked design doc, section 20 (\"least privilege service accounts\")."
}

variable "tags" {
  type    = map(string)
  default = {}
}
