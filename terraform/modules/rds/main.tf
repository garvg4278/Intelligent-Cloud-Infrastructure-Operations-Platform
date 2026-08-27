# RDS module: single Postgres instance, matching docker-compose.yml's
# `postgres:16-alpine` (same DB name/username convention: "icop"/"icop")
# but with the password generated and stored in Secrets Manager instead
# of hardcoded, per this platform's own "never store secrets in source
# code" principle (ROADMAP.md's linked design doc, section 20). Every
# ICOP service that has a DATABASE_URL today (auth, deployment, incident,
# alert, aiops, notification, audit, and now infrastructure) points at
# this one instance in real environments, same as they all point at the
# one shared `postgres` container in docker-compose -- see the root
# README's "Known simplifications" for why that's a deliberate, documented
# choice rather than an oversight.

resource "random_password" "master" {
  length  = 32
  special = false # RDS master passwords reject some special characters outright; simpler to avoid the class entirely than allowlist
}

resource "aws_secretsmanager_secret" "db" {
  name = "${var.name_prefix}-rds-master"
  tags = var.tags
}

resource "aws_secretsmanager_secret_version" "db" {
  secret_id = aws_secretsmanager_secret.db.id
  secret_string = jsonencode({
    username = var.master_username
    password = random_password.master.result
    engine   = "postgres"
    dbname   = var.db_name
  })
}

resource "aws_db_subnet_group" "this" {
  name       = "${var.name_prefix}-db-subnets"
  subnet_ids = var.private_subnet_ids
  tags       = var.tags
}

resource "aws_security_group" "db" {
  name        = "${var.name_prefix}-rds-sg"
  description = "Allows Postgres (5432) only from the EKS node security group -- nothing else in or outside the VPC can reach this database."
  vpc_id      = var.vpc_id

  ingress {
    description     = "Postgres from EKS nodes"
    from_port        = 5432
    to_port          = 5432
    protocol         = "tcp"
    security_groups  = var.allowed_security_group_ids
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-rds-sg" })
}

resource "aws_db_instance" "this" {
  identifier     = "${var.name_prefix}-postgres"
  engine         = "postgres"
  engine_version = var.engine_version
  instance_class = var.instance_class

  allocated_storage     = var.allocated_storage_gb
  max_allocated_storage = var.max_allocated_storage_gb
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = var.db_name
  username = var.master_username
  password = random_password.master.result

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [aws_security_group.db.id]
  publicly_accessible    = false # v6 of the AWS provider defaults this to false anyway; set explicitly since "nothing here is publicly reachable" is worth stating, not just relying on a provider default

  multi_az                = var.multi_az
  backup_retention_period  = var.backup_retention_days
  deletion_protection     = var.deletion_protection
  skip_final_snapshot     = var.skip_final_snapshot
  final_snapshot_identifier = var.skip_final_snapshot ? null : "${var.name_prefix}-postgres-final"

  # Alembic migrations (every service's alembic/env.py, see
  # services/*/alembic/env.py) run against whatever DATABASE_URL resolves
  # to -- this instance, once one is pointed at it via Secrets Manager
  # instead of the docker-compose default.
  tags = merge(var.tags, { Name = "${var.name_prefix}-postgres" })
}
