# Production environment. Same module set as staging, deliberately
# different choices at every point where "cheap and good enough" (staging)
# and "resilient" (production) diverge -- see each module { } block's
# inline comments for which argument encodes that and why. This is the
# same infrastructure shape reviewed and provisioned twice, not a
# different design -- that's the point of modules.

module "network" {
  source = "../../modules/network"

  name_prefix          = "icop-production"
  vpc_cidr              = var.vpc_cidr
  azs                    = var.azs
  public_subnet_cidrs   = var.public_subnet_cidrs
  private_subnet_cidrs  = var.private_subnet_cidrs
  single_nat_gateway    = false # production: one NAT gateway per AZ -- an AZ outage shouldn't take every other AZ's outbound traffic down with it
}

module "eks" {
  source = "../../modules/eks"

  name_prefix                    = "icop-production"
  cluster_version                 = var.eks_cluster_version
  vpc_id                          = module.network.vpc_id
  private_subnet_ids             = module.network.private_subnet_ids
  public_subnet_ids              = module.network.public_subnet_ids
  cluster_endpoint_public_access = true # see this module's variable description if you have a VPN/bastion and want to flip this false

  node_instance_types = var.node_instance_types
  node_desired_size    = var.node_desired_size
  node_min_size        = var.node_desired_size
  node_max_size        = var.node_max_size
  node_capacity_type  = "ON_DEMAND" # production: no spot interruptions
}

module "rds" {
  source = "../../modules/rds"

  name_prefix                = "icop-production"
  vpc_id                      = module.network.vpc_id
  private_subnet_ids         = module.network.private_subnet_ids
  allowed_security_group_ids = [module.eks.cluster_security_group_id]

  instance_class          = var.db_instance_class
  multi_az                 = true  # production: automatic failover to a standby in a second AZ
  deletion_protection     = true  # production: `terraform destroy` on this resource fails closed until deliberately disabled
  skip_final_snapshot     = false # production: a destroy always leaves a recoverable snapshot behind
  backup_retention_days   = 30
}

module "elasticache" {
  source = "../../modules/elasticache"

  name_prefix                = "icop-production"
  vpc_id                      = module.network.vpc_id
  private_subnet_ids         = module.network.private_subnet_ids
  allowed_security_group_ids = [module.eks.cluster_security_group_id]

  node_type       = var.redis_node_type
  num_cache_nodes = 2 # production: primary + replica, automatic_failover_enabled derives to true at 2+ (see the module)
}

module "object_storage" {
  source = "../../modules/object_storage"

  name_prefix        = "icop-production"
  versioning_enabled = true
  force_destroy       = false # production: terraform destroy must fail rather than silently drop objects
}

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

  role_name             = "icop-production-deployment-artifacts"
  oidc_provider_arn     = module.eks.oidc_provider_arn
  oidc_provider_url     = module.eks.oidc_provider_url
  namespace              = "icop-production"
  service_account_name  = "deployment-worker"
  policy_json            = data.aws_iam_policy_document.deployment_artifacts.json
}
