output "db_endpoint" {
  value = aws_db_instance.this.address
}

output "db_port" {
  value = aws_db_instance.this.port
}

output "db_name" {
  value = aws_db_instance.this.db_name
}

output "secret_arn" {
  description = "Secrets Manager ARN holding username/password/engine/dbname as JSON -- read this at deploy time (e.g. via the External Secrets Operator, or Ansible's community.aws.secretsmanager_secret lookup) to build each service's real DATABASE_URL. Never interpolated into a DATABASE_URL by Terraform itself, which would put the password in plan/state output."
  value       = aws_secretsmanager_secret.db.arn
}

output "security_group_id" {
  value = aws_security_group.db.id
}
