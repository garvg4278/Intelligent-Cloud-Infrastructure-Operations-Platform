# Staging environment: wires network -> eks -> rds -> elasticache ->
# object_storage -> irsa together. This is the concrete thing
# `terraform/bootstrap`'s state bucket exists to hold state for, and the
# concrete thing the `infrastructure` service's TerraformOrchestrator
# targets when a user creates a "staging" environment through the API
# (see services/infrastructure/app/terraform_orchestrator.py).
#
# Per-resource tags: deliberately not passed to every module call here --
# the aws provider's default_tags block in versions.tf already stamps
# Project/Environment/ManagedBy onto everything this config creates, so
# repeating {Environment = "staging"} into six module blocks would just
# be the same fact written seven times.

module "network" {
  source = "../../modules/network"

  name_prefix           = "icop-staging"
  vpc_cidr               = var.vpc_cidr
  azs                     = var.azs
  public_subnet_cidrs    = var.public_subnet_cidrs
  private_subnet_cidrs   = var.private_subnet_cidrs
  single_nat_gateway     = true # staging: one NAT gateway is an acceptable single point of failure for the money saved
}

module "eks" {
  source = "../../modules/eks"

  name_prefix                    = "icop-staging"
  cluster_version                 = var.eks_cluster_version
  vpc_id                          = module.network.vpc_id
  private_subnet_ids             = module.network.private_subnet_ids
  public_subnet_ids              = module.network.public_subnet_ids
  cluster_endpoint_public_access = true

  node_instance_types = var.node_instance_types
  node_desired_size    = var.node_desired_size
  node_min_size        = 1
  node_max_size        = var.node_desired_size + 2
  node_capacity_type  = "SPOT" # staging only -- environments/production overrides to ON_DEMAND
}

module "rds" {
  source = "../../modules/rds"

  name_prefix                = "icop-staging"
  vpc_id                      = module.network.vpc_id
  private_subnet_ids         = module.network.private_subnet_ids
  allowed_security_group_ids = [module.eks.cluster_security_group_id]

  instance_class        = var.db_instance_class
  multi_az               = false
  deletion_protection    = false
  skip_final_snapshot   = true # staging: destroy shouldn't hang on a snapshot
}

module "elasticache" {
  source = "../../modules/elasticache"

  name_prefix                = "icop-staging"
  vpc_id                      = module.network.vpc_id
  private_subnet_ids         = module.network.private_subnet_ids
  allowed_security_group_ids = [module.eks.cluster_security_group_id]

  node_type       = var.redis_node_type
  num_cache_nodes = 1 # staging: no replica
}

module "object_storage" {
  source = "../../modules/object_storage"

  name_prefix        = "icop-staging"
  versioning_enabled = true
  force_destroy       = true # staging: allow terraform destroy to clean up even with objects present
}

# Scoped S3 access for the deployment service -- the one real, named use
# case for pod-level AWS permissions today (see
# terraform/modules/irsa/README.md for what's still missing on the
# Kubernetes side to actually consume this).
data "aws_iam_policy_document" "deployment_artifacts" {
  statement {
    effect  = "Allow"
    actions = ["s3:GetObject", "s3:PutObject", "s3:ListBucket"]
    resources = [
      module.object_storage.bucket_arn,
      "${module.object_storage.bucket_arn}/*",
    ]
  }
}

module "deployment_irsa" {
  source = "../../modules/irsa"

  role_name             = "icop-staging-deployment-artifacts"
  oidc_provider_arn     = module.eks.oidc_provider_arn
  oidc_provider_url     = module.eks.oidc_provider_url
  namespace              = "icop-staging"
  service_account_name  = "deployment-worker"
  policy_json            = data.aws_iam_policy_document.deployment_artifacts.json
}
