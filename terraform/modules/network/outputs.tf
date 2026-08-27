output "vpc_id" {
  value = aws_vpc.this.id
}

output "vpc_cidr" {
  value = aws_vpc.this.cidr_block
}

output "public_subnet_ids" {
  value = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  value = aws_subnet.private[*].id
}

output "nat_gateway_ips" {
  description = "Public IP(s) of the NAT gateway(s) -- useful if a downstream system needs an IP allowlist entry for this environment's outbound traffic."
  value       = aws_eip.nat[*].public_ip
}
