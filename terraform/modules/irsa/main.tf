# IRSA (IAM Roles for Service Accounts) module: lets one specific
# Kubernetes ServiceAccount, in one specific namespace, assume one
# specific IAM role with no long-lived AWS credentials anywhere -- no
# access key baked into a Secret, nothing for `services/audit` to have to
# log a leak of. The EKS Pod Identity webhook (installed automatically on
# every EKS cluster since ~2021) injects short-lived, auto-rotating STS
# credentials into any pod running as the trusted service account.
#
# The trust policy below is what makes this scoped to exactly one
# ServiceAccount rather than "anything in the cluster" -- the
# StringEquals condition checks both the subject (namespace:service
# account name) AND the audience, which is the actual security boundary;
# getting the condition keys wrong (e.g. using StringLike with a wildcard
# subject) is the most common way this pattern gets accidentally
# over-broadened, so this module deliberately doesn't expose that as a
# variable at all.

data "aws_iam_policy_document" "trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [var.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${var.oidc_provider_url}:sub"
      values   = ["system:serviceaccount:${var.namespace}:${var.service_account_name}"]
    }

    condition {
      test     = "StringEquals"
      variable = "${var.oidc_provider_url}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "this" {
  name               = var.role_name
  assume_role_policy = data.aws_iam_policy_document.trust.json
  tags               = var.tags
}

resource "aws_iam_role_policy" "this" {
  name   = "${var.role_name}-policy"
  role   = aws_iam_role.this.id
  policy = var.policy_json
}
