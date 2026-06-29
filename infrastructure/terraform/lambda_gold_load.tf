resource "aws_security_group" "gold_load_lambda" {
  name        = "${local.name_prefix}-gold-load-lambda-sg"
  description = "Gold-to-Postgres load Lambda"
  vpc_id      = aws_vpc.main.id

  egress {
    description = "HTTPS for CloudWatch and AWS APIs"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${local.name_prefix}-gold-load-lambda-sg"
  }
}

resource "aws_vpc_security_group_egress_rule" "gold_load_postgres_to_analytics" {
  security_group_id            = aws_security_group.gold_load_lambda.id
  referenced_security_group_id = aws_security_group.analytics_ec2.id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
  description                  = "PostgreSQL to analytics EC2"
}

resource "aws_vpc_security_group_ingress_rule" "analytics_postgres_from_vpc" {
  security_group_id = aws_security_group.analytics_ec2.id
  cidr_ipv4         = aws_vpc.main.cidr_block
  from_port         = 5432
  to_port           = 5432
  ip_protocol       = "tcp"
  description       = "PostgreSQL from VPC (Lambda in private subnets)"
}

resource "aws_vpc_security_group_ingress_rule" "analytics_postgres_from_lambda" {
  security_group_id            = aws_security_group.analytics_ec2.id
  referenced_security_group_id = aws_security_group.gold_load_lambda.id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
  description                  = "PostgreSQL from gold load Lambda"
}

data "archive_file" "gold_to_postgres_lambda" {
  type        = "zip"
  source_dir  = "${path.module}/../../lambdas/gold_to_postgres"
  output_path = "${path.module}/../../dist/gold_to_postgres.zip"
}

resource "aws_iam_role" "gold_to_postgres_lambda" {
  name = "${local.name_prefix}-gold-to-postgres-lambda"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy" "gold_to_postgres_lambda" {
  name = "${local.name_prefix}-gold-to-postgres-lambda"
  role = aws_iam_role.gold_to_postgres_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "GoldRead"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket",
        ]
        Resource = [
          aws_s3_bucket.data_lake.arn,
          "${aws_s3_bucket.data_lake.arn}/gold/*",
        ]
      },
      {
        Sid    = "Logs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ]
        Resource = "arn:aws:logs:${var.aws_region}:${local.account_id}:*"
      },
      {
        Sid    = "VpcNetworking"
        Effect = "Allow"
        Action = [
          "ec2:CreateNetworkInterface",
          "ec2:DescribeNetworkInterfaces",
          "ec2:DeleteNetworkInterface",
          "ec2:AssignPrivateIpAddresses",
          "ec2:UnassignPrivateIpAddresses",
        ]
        Resource = "*"
      },
    ]
  })
}

resource "aws_cloudwatch_log_group" "gold_to_postgres_lambda" {
  name              = "/aws/lambda/${local.name_prefix}-gold-to-postgres"
  retention_in_days = 14
}

resource "aws_lambda_function" "gold_to_postgres" {
  function_name = "${local.name_prefix}-gold-to-postgres"
  role          = aws_iam_role.gold_to_postgres_lambda.arn
  handler       = "handler.lambda_handler"
  runtime       = "python3.12"
  timeout       = var.gold_load_lambda_timeout
  memory_size   = var.gold_load_lambda_memory

  filename         = data.archive_file.gold_to_postgres_lambda.output_path
  source_code_hash = data.archive_file.gold_to_postgres_lambda.output_base64sha256

  layers = [var.awswrangler_layer_arn]

  environment {
    variables = {
      DATA_LAKE_BUCKET = aws_s3_bucket.data_lake.id
      GOLD_PREFIX      = "gold"
      POSTGRES_HOST    = aws_instance.analytics.private_ip
      POSTGRES_PORT    = "5432"
      POSTGRES_USER    = "medallion"
      POSTGRES_PASSWORD = local.postgres_password
      POSTGRES_DB      = "medallion"
    }
  }

  vpc_config {
    subnet_ids         = aws_subnet.private[*].id
    security_group_ids = [aws_security_group.gold_load_lambda.id]
  }

  depends_on = [
    aws_cloudwatch_log_group.gold_to_postgres_lambda,
    aws_iam_role_policy.gold_to_postgres_lambda,
    aws_nat_gateway.main,
    aws_instance.analytics,
  ]

  tags = {
    Layer = "visualization"
  }
}

resource "aws_cloudwatch_event_rule" "gold_to_postgres_schedule" {
  name                = "${local.name_prefix}-gold-to-postgres-daily"
  description         = "Load gold Parquet metrics into PostgreSQL for Superset"
  schedule_expression = var.gold_load_schedule
}

resource "aws_cloudwatch_event_target" "gold_to_postgres_schedule" {
  rule      = aws_cloudwatch_event_rule.gold_to_postgres_schedule.name
  target_id = "gold-to-postgres"
  arn       = aws_lambda_function.gold_to_postgres.arn
}

resource "aws_lambda_permission" "eventbridge_gold_to_postgres" {
  statement_id  = "AllowEventBridgeInvokeGoldLoad"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.gold_to_postgres.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.gold_to_postgres_schedule.arn
}
