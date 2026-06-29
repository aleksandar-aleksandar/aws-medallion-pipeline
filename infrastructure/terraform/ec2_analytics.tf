resource "random_password" "postgres" {
  length  = 24
  special = false
}

resource "random_password" "superset_secret" {
  length  = 48
  special = true
}

locals {
  postgres_password       = coalesce(var.postgres_password, random_password.postgres.result)
  superset_secret_key     = random_password.superset_secret.result
  superset_admin_password = coalesce(var.superset_admin_password, "MedallionAdmin123!")
  docker_compose_content  = file("${path.module}/../ec2/docker-compose.yml")
  analytics_bootstrap = templatefile("${path.module}/../ec2/bootstrap.sh.tpl", {
    postgres_password       = local.postgres_password
    superset_secret_key     = local.superset_secret_key
    superset_admin_password = local.superset_admin_password
    docker_compose_content  = local.docker_compose_content
  })
}

data "aws_ami" "amazon_linux_2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

resource "aws_security_group" "analytics_ec2" {
  name        = "${local.name_prefix}-analytics-ec2-sg"
  description = "PostgreSQL + Superset on analytics EC2"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "Superset UI"
    from_port   = 8088
    to_port     = 8088
    protocol    = "tcp"
    cidr_blocks = [var.superset_allowed_cidr]
  }

  egress {
    description = "Docker image pulls and updates"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "HTTP for package mirrors"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${local.name_prefix}-analytics-ec2-sg"
  }
}

resource "aws_iam_role" "analytics_ec2" {
  name = "${local.name_prefix}-analytics-ec2"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ec2.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "analytics_ec2_ssm" {
  role       = aws_iam_role.analytics_ec2.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "analytics_ec2" {
  name = "${local.name_prefix}-analytics-ec2"
  role = aws_iam_role.analytics_ec2.name
}

resource "aws_instance" "analytics" {
  ami                         = data.aws_ami.amazon_linux_2023.id
  instance_type               = var.analytics_instance_type
  subnet_id                   = aws_subnet.public[0].id
  vpc_security_group_ids      = [aws_security_group.analytics_ec2.id]
  iam_instance_profile        = aws_iam_instance_profile.analytics_ec2.name
  associate_public_ip_address = true

  user_data = base64encode(local.analytics_bootstrap)

  root_block_device {
    volume_size = 30
    volume_type = "gp3"
  }

  tags = {
    Name = "${local.name_prefix}-analytics"
    Role = "superset-postgres"
  }
}

resource "aws_eip" "analytics" {
  domain = "vpc"

  tags = {
    Name = "${local.name_prefix}-analytics-eip"
  }
}

resource "aws_eip_association" "analytics" {
  instance_id   = aws_instance.analytics.id
  allocation_id = aws_eip.analytics.id
}
