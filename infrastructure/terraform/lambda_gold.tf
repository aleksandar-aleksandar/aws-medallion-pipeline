data "archive_file" "gold_transform_lambda" {
  type        = "zip"
  source_dir  = "${path.module}/../../lambdas/gold_transform"
  output_path = "${path.module}/../../dist/gold_transform.zip"
}

resource "aws_iam_role" "gold_transform_lambda" {
  name = "${local.name_prefix}-gold-transform-lambda"

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

resource "aws_iam_role_policy" "gold_transform_lambda" {
  name = "${local.name_prefix}-gold-transform-lambda"
  role = aws_iam_role.gold_transform_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "SilverRead"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket",
        ]
        Resource = [
          aws_s3_bucket.data_lake.arn,
          "${aws_s3_bucket.data_lake.arn}/silver/*",
        ]
      },
      {
        Sid    = "GoldWrite"
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:AbortMultipartUpload",
        ]
        Resource = "${aws_s3_bucket.data_lake.arn}/gold/*"
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

resource "aws_cloudwatch_log_group" "gold_transform_lambda" {
  name              = "/aws/lambda/${local.name_prefix}-gold-transform"
  retention_in_days = 14
}

resource "aws_lambda_function" "gold_transform" {
  function_name = "${local.name_prefix}-gold-transform"
  role          = aws_iam_role.gold_transform_lambda.arn
  handler       = "handler.lambda_handler"
  runtime       = "python3.12"
  timeout       = var.gold_lambda_timeout
  memory_size   = var.gold_lambda_memory

  filename         = data.archive_file.gold_transform_lambda.output_path
  source_code_hash = data.archive_file.gold_transform_lambda.output_base64sha256

  layers = [var.awswrangler_layer_arn]

  environment {
    variables = {
      DATA_LAKE_BUCKET = aws_s3_bucket.data_lake.id
      SILVER_PREFIX    = "silver"
      GOLD_PREFIX      = "gold"
    }
  }

  vpc_config {
    subnet_ids         = aws_subnet.private[*].id
    security_group_ids = [aws_security_group.lambda_hn.id]
  }

  depends_on = [
    aws_cloudwatch_log_group.gold_transform_lambda,
    aws_iam_role_policy.gold_transform_lambda,
    aws_nat_gateway.main,
  ]

  tags = {
    Layer = "gold"
  }
}

resource "aws_cloudwatch_event_rule" "gold_transform_schedule" {
  name                = "${local.name_prefix}-gold-transform-daily"
  description         = "Daily gold metrics after silver normalization"
  schedule_expression = var.gold_transform_schedule
}

resource "aws_cloudwatch_event_target" "gold_transform_schedule" {
  rule      = aws_cloudwatch_event_rule.gold_transform_schedule.name
  target_id = "gold-transform"
  arn       = aws_lambda_function.gold_transform.arn
}

resource "aws_lambda_permission" "eventbridge_gold_transform" {
  statement_id  = "AllowEventBridgeInvokeGold"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.gold_transform.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.gold_transform_schedule.arn
}
