data "archive_file" "silver_normalize_lambda" {
  type        = "zip"
  source_dir  = "${path.module}/../../lambdas/silver_normalize"
  output_path = "${path.module}/../../dist/silver_normalize.zip"
}

resource "aws_iam_role" "silver_normalize_lambda" {
  name = "${local.name_prefix}-silver-normalize-lambda"

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

resource "aws_iam_role_policy" "silver_normalize_lambda" {
  name = "${local.name_prefix}-silver-normalize-lambda"
  role = aws_iam_role.silver_normalize_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "BronzeRead"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket",
        ]
        Resource = [
          aws_s3_bucket.data_lake.arn,
          "${aws_s3_bucket.data_lake.arn}/bronze/*",
        ]
      },
      {
        Sid    = "SilverWrite"
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:AbortMultipartUpload",
        ]
        Resource = "${aws_s3_bucket.data_lake.arn}/silver/*"
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

resource "aws_cloudwatch_log_group" "silver_normalize_lambda" {
  name              = "/aws/lambda/${local.name_prefix}-silver-normalize"
  retention_in_days = 14
}

resource "aws_lambda_function" "silver_normalize" {
  function_name = "${local.name_prefix}-silver-normalize"
  role          = aws_iam_role.silver_normalize_lambda.arn
  handler       = "handler.lambda_handler"
  runtime       = "python3.12"
  timeout       = var.silver_lambda_timeout
  memory_size   = var.silver_lambda_memory

  filename         = data.archive_file.silver_normalize_lambda.output_path
  source_code_hash = data.archive_file.silver_normalize_lambda.output_base64sha256

  layers = [var.awswrangler_layer_arn]

  environment {
    variables = {
      DATA_LAKE_BUCKET = aws_s3_bucket.data_lake.id
      BRONZE_PREFIX    = "bronze"
      SILVER_PREFIX    = "silver"
      PROCESS_X        = "true"
    }
  }

  vpc_config {
    subnet_ids         = aws_subnet.private[*].id
    security_group_ids = [aws_security_group.lambda_hn.id]
  }

  depends_on = [
    aws_cloudwatch_log_group.silver_normalize_lambda,
    aws_iam_role_policy.silver_normalize_lambda,
    aws_nat_gateway.main,
  ]

  tags = {
    Layer = "silver"
  }
}

resource "aws_cloudwatch_event_rule" "silver_normalize_schedule" {
  name                = "${local.name_prefix}-silver-normalize-daily"
  description         = "Daily silver normalization after bronze HN ingest"
  schedule_expression = var.silver_normalize_schedule
}

resource "aws_cloudwatch_event_target" "silver_normalize_schedule" {
  rule      = aws_cloudwatch_event_rule.silver_normalize_schedule.name
  target_id = "silver-normalize"
  arn       = aws_lambda_function.silver_normalize.arn
}

resource "aws_lambda_permission" "eventbridge_silver_normalize" {
  statement_id  = "AllowEventBridgeInvokeSilver"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.silver_normalize.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.silver_normalize_schedule.arn
}
