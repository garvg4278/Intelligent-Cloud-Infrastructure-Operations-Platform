output "redis_endpoint" {
  description = "Primary endpoint -- use this directly for single-node (num_cache_nodes = 1); for multi-node it's still correct (points at the current primary) but reader_endpoint below is also available for read traffic."
  value       = aws_elasticache_replication_group.this.primary_endpoint_address
}

output "reader_endpoint" {
  value = try(aws_elasticache_replication_group.this.reader_endpoint_address, null)
}

output "redis_port" {
  value = aws_elasticache_replication_group.this.port
}

output "security_group_id" {
  value = aws_security_group.redis.id
}
