# EKS module: control plane, one managed node group, and the OIDC identity
# provider that IRSA (terraform/modules/irsa) needs to exist before it can
# hand out pod-scoped IAM roles. This is the module the original design
# doc's "Kubernetes cluster is registered" step (ROADMAP.md's linked
# design doc, section 6.4) resolves to: after this module applies, there
# is a real EKS cluster for the deployment service's HelmOrchestrator and
# the infrastructure service's Ansible run to both target.

data "aws_caller_identity" "current" {}

# ---- Cluster IAM role -------------------------------------------------

resource "aws_iam_role" "cluster" {
  name = "${var.name_prefix}-eks-cluster"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "eks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "cluster_policy" {
  role       = aws_iam_role.cluster.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
}

# ---- Cluster --------------------------------------------------------

resource "aws_security_group" "cluster" {
  name        = "${var.name_prefix}-eks-cluster-sg"
  description = "Additional SG attached to the EKS control plane ENIs, on top of the one EKS creates automatically. Empty of rules today -- a placeholder for things like a future bastion-to-API rule -- but declared here so downstream modules (irsa, and any future bastion module) have a stable SG id to reference."
  vpc_id      = var.vpc_id
  tags        = merge(var.tags, { Name = "${var.name_prefix}-eks-cluster-sg" })
}

resource "aws_eks_cluster" "this" {
  name     = var.name_prefix
  role_arn = aws_iam_role.cluster.arn
  version  = var.cluster_version

  vpc_config {
    subnet_ids              = concat(var.private_subnet_ids, var.public_subnet_ids)
    security_group_ids      = [aws_security_group.cluster.id]
    endpoint_public_access  = var.cluster_endpoint_public_access
    endpoint_private_access = true # always on: in-VPC access (the deployment/infrastructure workers, if run as EKS pods themselves later) never depends on the public endpoint toggle
  }

  # Full control-plane audit trail -- "audit logging" is a named security
  # control in this platform's own design (ROADMAP.md's linked design doc,
  # section 20), and that applies to the cluster control plane too, not
  # just the ICOP services' own /audit/events.
  enabled_cluster_log_types = ["api", "audit", "authenticator", "controllerManager", "scheduler"]

  depends_on = [aws_iam_role_policy_attachment.cluster_policy]

  tags = var.tags
}

resource "aws_cloudwatch_log_group" "cluster" {
  name              = "/aws/eks/${var.name_prefix}/cluster"
  retention_in_days = 30
  tags              = var.tags
}

# ---- OIDC provider (IRSA prerequisite) --------------------------------

data "tls_certificate" "eks" {
  url = aws_eks_cluster.this.identity[0].oidc[0].issuer
}

resource "aws_iam_openid_connect_provider" "eks" {
  url             = aws_eks_cluster.this.identity[0].oidc[0].issuer
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.eks.certificates[0].sha1_fingerprint]
  tags            = var.tags
}

# ---- Node group IAM role ----------------------------------------------

resource "aws_iam_role" "node" {
  name = "${var.name_prefix}-eks-node"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "node_worker" {
  role       = aws_iam_role.node.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
}

resource "aws_iam_role_policy_attachment" "node_cni" {
  role       = aws_iam_role.node.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
}

resource "aws_iam_role_policy_attachment" "node_ecr_readonly" {
  role       = aws_iam_role.node.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

resource "aws_iam_role_policy_attachment" "node_ssm" {
  # The EKS-optimized AL2023 AMI ships the SSM Agent already running; this
  # attachment is the only thing missing for it to actually register with
  # Systems Manager. Once it does, Ansible (../../ansible/) can reach every
  # node over SSM Session Manager -- no SSH keypair, no bastion host, no
  # port 22 open anywhere (this module's node security group, managed by
  # EKS itself, has no ingress rule for it). See ../../ansible/README.md.
  role       = aws_iam_role.node.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# ---- Managed node group -------------------------------------------------

resource "aws_eks_node_group" "default" {
  cluster_name    = aws_eks_cluster.this.name
  node_group_name = "${var.name_prefix}-default"
  node_role_arn   = aws_iam_role.node.arn
  subnet_ids      = var.private_subnet_ids # nodes are never in a public subnet

  instance_types = var.node_instance_types
  capacity_type  = var.node_capacity_type

  scaling_config {
    desired_size = var.node_desired_size
    min_size     = var.node_min_size
    max_size     = var.node_max_size
  }

  update_config {
    max_unavailable = 1
  }

  labels = {
    "icop.io/node-pool" = "default"
  }

  depends_on = [
    aws_iam_role_policy_attachment.node_worker,
    aws_iam_role_policy_attachment.node_cni,
    aws_iam_role_policy_attachment.node_ecr_readonly,
    aws_iam_role_policy_attachment.node_ssm,
  ]

  tags = var.tags

  lifecycle {
    # A desired_size change from manual scaling or an HPA-triggered cluster
    # autoscaler action shouldn't be treated as configuration drift on the
    # next `terraform plan` -- only min/max are meant to be Terraform-owned
    # once the cluster is live.
    ignore_changes = [scaling_config[0].desired_size]
  }
}
