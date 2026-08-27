# Network module: VPC, public + private subnets across the given AZs, one
# internet gateway, and either one shared NAT gateway or one per AZ
# (var.single_nat_gateway). Deliberately does not create any security
# groups of its own -- those are scoped to what actually needs them (EKS
# nodes, RDS, ElastiCache) and live in each of those modules instead, so
# this module's only job is IP address space and routing, matching the
# "each subsystem should do one job well" principle the rest of this repo
# follows (see ROADMAP.md's original design doc, section 5.1).

locals {
  az_count = length(var.azs)
}

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true # required for EKS -- pods/nodes resolve AWS service endpoints by name

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-vpc"
  })
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-igw"
  })
}

resource "aws_subnet" "public" {
  count                   = local.az_count
  vpc_id                  = aws_vpc.this.id
  cidr_block              = var.public_subnet_cidrs[count.index]
  availability_zone       = var.azs[count.index]
  map_public_ip_on_launch = true

  tags = merge(var.tags, {
    Name                     = "${var.name_prefix}-public-${var.azs[count.index]}"
    "kubernetes.io/role/elb" = "1" # lets an in-cluster Service type=LoadBalancer pick these subnets automatically
  })
}

resource "aws_subnet" "private" {
  count             = local.az_count
  vpc_id            = aws_vpc.this.id
  cidr_block        = var.private_subnet_cidrs[count.index]
  availability_zone = var.azs[count.index]

  tags = merge(var.tags, {
    Name                              = "${var.name_prefix}-private-${var.azs[count.index]}"
    "kubernetes.io/role/internal-elb" = "1"
    # EKS's cluster autoscaler / karpenter discover subnets via this tag if
    # you add either later -- harmless to set now even though this repo
    # doesn't provision either yet.
    "kubernetes.io/cluster/${var.name_prefix}" = "shared"
  })
}

resource "aws_eip" "nat" {
  # v6 of the AWS provider removed the old `vpc = true` argument -- a
  # NAT-gateway EIP is always a VPC-scoped one now, no argument needed for
  # that; see the provider's v6 upgrade guide.
  count = var.single_nat_gateway ? 1 : local.az_count

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-nat-eip-${count.index}"
  })

  depends_on = [aws_internet_gateway.this]
}

resource "aws_nat_gateway" "this" {
  count         = var.single_nat_gateway ? 1 : local.az_count
  allocation_id = aws_eip.nat[count.index].id
  # Single-NAT mode: everything routes through the first public subnet.
  # Per-AZ mode: NAT gateway i lives in public subnet i, so private subnet
  # i's traffic never has to cross an AZ boundary just to reach the internet.
  subnet_id = aws_subnet.public[count.index].id

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-nat-${count.index}"
  })

  depends_on = [aws_internet_gateway.this]
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-public-rt"
  })
}

resource "aws_route_table_association" "public" {
  count          = local.az_count
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# One private route table per AZ even in single-NAT mode (all pointing at
# the same NAT gateway) -- keeps this module's shape identical between
# single- and per-AZ-NAT modes, so switching var.single_nat_gateway later
# doesn't change the number of route tables, only which NAT each points at.
resource "aws_route_table" "private" {
  count  = local.az_count
  vpc_id = aws_vpc.this.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = var.single_nat_gateway ? aws_nat_gateway.this[0].id : aws_nat_gateway.this[count.index].id
  }

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-private-rt-${var.azs[count.index]}"
  })
}

resource "aws_route_table_association" "private" {
  count          = local.az_count
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private[count.index].id
}
