data "archive_file" "hn_bronze_lambda" {
  type        = "zip"
  source_dir  = "${path.module}/../../lambdas/hn_bronze_ingest"
  output_path = "${path.module}/../../dist/hn_bronze_ingest.zip"
}

resource "aws_iam_role" "hn_bronze_lambda" {
  name = "${local.name_prefix}-hn-bronze-lambda"

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

resource "aws_iam_role_policy" "hn_bronze_lambda" {
  name = "${local.name_prefix}-hn-bronze-lambda"
  role = aws_iam_role.hn_bronze_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "BronzeWrite"
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:AbortMultipartUpload",
        ]
        Resource = "${aws_s3_bucket.data_lake.arn}/bronze/hackernews/*"
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

resource "aws_cloudwatch_log_group" "hn_bronze_lambda" {
  name              = "/aws/lambda/${local.name_prefix}-hn-bronze-ingest"
  retention_in_days = 14
}

resource "aws_lambda_function" "hn_bronze_ingest" {
  function_name = "${local.name_prefix}-hn-bronze-ingest"
  role          = aws_iam_role.hn_bronze_lambda.arn
  handler       = "handler.lambda_handler"
  runtime       = "python3.12"
  timeout       = var.hn_lambda_timeout
  memory_size   = var.hn_lambda_memory

  filename         = data.archive_file.hn_bronze_lambda.output_path
  source_code_hash = data.archive_file.hn_bronze_lambda.output_base64sha256

  environment {
    variables = {
      DATA_LAKE_BUCKET = aws_s3_bucket.data_lake.id
      BRONZE_PREFIX    = "bronze"
    }
  }

  vpc_config {
    subnet_ids         = aws_subnet.private[*].id
    security_group_ids = [aws_security_group.lambda_hn.id]
  }

  depends_on = [
    aws_cloudwatch_log_group.hn_bronze_lambda,
    aws_iam_role_policy.hn_bronze_lambda,
    aws_nat_gateway.main,
  ]

  tags = {
    Layer = "bronze"
  }
}

resource "aws_lambda_permission" "eventbridge_hn_bronze" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.hn_bronze_ingest.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.hn_bronze_schedule.arn
}
