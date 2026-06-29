data "archive_file" "discord_notify_lambda" {
  count = local.discord_notifications_enabled ? 1 : 0

  type        = "zip"
  source_dir  = "${path.module}/../../lambdas/discord_notify"
  output_path = "${path.module}/../../dist/discord_notify.zip"
}

resource "aws_iam_role" "discord_notify_lambda" {
  count = local.discord_notifications_enabled ? 1 : 0

  name = "${local.name_prefix}-discord-notify-lambda"

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

resource "aws_iam_role_policy" "discord_notify_lambda" {
  count = local.discord_notifications_enabled ? 1 : 0

  name = "${local.name_prefix}-discord-notify-lambda"
  role = aws_iam_role.discord_notify_lambda[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "Logs"
      Effect = "Allow"
      Action = [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents",
      ]
      Resource = "arn:aws:logs:${var.aws_region}:${local.account_id}:*"
    }]
  })
}

resource "aws_cloudwatch_log_group" "discord_notify_lambda" {
  count = local.discord_notifications_enabled ? 1 : 0

  name              = "/aws/lambda/${local.name_prefix}-discord-notify"
  retention_in_days = 14
}

resource "aws_lambda_function" "discord_notify" {
  count = local.discord_notifications_enabled ? 1 : 0

  function_name = "${local.name_prefix}-discord-notify"
  role          = aws_iam_role.discord_notify_lambda[0].arn
  handler       = "handler.lambda_handler"
  runtime       = "python3.12"
  timeout       = 30
  memory_size   = 128

  filename         = data.archive_file.discord_notify_lambda[0].output_path
  source_code_hash = data.archive_file.discord_notify_lambda[0].output_base64sha256

  environment {
    variables = {
      DISCORD_WEBHOOK_URL = var.discord_webhook_url
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.discord_notify_lambda,
    aws_iam_role_policy.discord_notify_lambda,
  ]

  tags = {
    Layer = "notifications"
  }
}

resource "aws_sns_topic" "pipeline_alerts" {
  count = local.discord_notifications_enabled ? 1 : 0

  name = "${local.name_prefix}-pipeline-alerts"
}

resource "aws_lambda_permission" "sns_discord_notify" {
  count = local.discord_notifications_enabled ? 1 : 0

  statement_id  = "AllowSNSInvokeDiscordNotify"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.discord_notify[0].function_name
  principal     = "sns.amazonaws.com"
  source_arn    = aws_sns_topic.pipeline_alerts[0].arn
}

resource "aws_sns_topic_subscription" "discord_notify" {
  count = local.discord_notifications_enabled ? 1 : 0

  topic_arn = aws_sns_topic.pipeline_alerts[0].arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.discord_notify[0].arn
}

locals {
  discord_notifications_enabled = nonsensitive(var.discord_webhook_url) != ""
  monitored_lambdas = {
    hn_bronze  = aws_lambda_function.hn_bronze_ingest.function_name
    silver     = aws_lambda_function.silver_normalize.function_name
    gold       = aws_lambda_function.gold_transform.function_name
    gold_to_pg = aws_lambda_function.gold_to_postgres.function_name
  }
}

resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  for_each = local.discord_notifications_enabled ? local.monitored_lambdas : {}

  alarm_name          = "${local.name_prefix}-${each.key}-errors"
  alarm_description   = "Discord alert when ${each.value} reports Lambda Errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 60
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = each.value
  }

  alarm_actions = [aws_sns_topic.pipeline_alerts[0].arn]
}
