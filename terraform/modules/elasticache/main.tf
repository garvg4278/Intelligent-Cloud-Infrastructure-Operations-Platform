# ElastiCache module: Redis, matching docker-compose.yml's `redis:7-alpine`
# single instance in shape, but as a real replication group so
# environments/production can turn on Multi-AZ automatic failover just by
# raising num_cache_nodes -- the resource type doesn't change between
# staging and production, only its size does.
#
# What actually uses this today: the gateway service's rate limiter
# (services/gateway/app/... -- REDIS_URL) is the only real Redis
# consumer in this repo right now. The original design doc's other
# proposed uses (job status cache, short-lived AI context, throttling
# counters -- see ROADMAP.md's linked design doc, section 7.2) aren't
# built yet; this module exists so there's somewhere real for the
# gateway's actual, current Redis dependency to point at in a real
# environment, not because every one of those proposed uses is live.

resource "aws_elasticache_subnet_group" "this" {
  name       = "${var.name_prefix}-redis-subnets"
  subnet_ids = var.private_subnet_ids
  tags       = var.tags
}

resource "aws_security_group" "redis" {
  name        = "${var.name_prefix}-redis-sg"
  description = "Allows Redis (6379) only from the EKS node security group."
  vpc_id      = var.vpc_id

  ingress {
    description     = "Redis from EKS nodes"
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = var.allowed_security_group_ids
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-redis-sg" })
}

resource "aws_elasticache_replication_group" "this" {
  replication_group_id = "${var.name_prefix}-redis"
  description           = "ICOP Redis (${var.name_prefix}) -- gateway rate limiting today; job-status cache / throttling counters if those get built"

  engine         = "redis"
  engine_version = var.engine_version
  node_type      = var.node_type

  num_cache_clusters = var.num_cache_nodes
  # Failover requires >= 2 nodes -- ElastiCache rejects this combination
  # outright with 1 node, so it's derived rather than a separate variable
  # someone could set inconsistently.
  automatic_failover_enabled = var.num_cache_nodes > 1

  subnet_group_name = aws_elasticache_subnet_group.this.name
  security_group_ids = [aws_security_group.redis.id]

  at_rest_encryption_enabled = true
  transit_encryption_enabled = true

  tags = var.tags
}
