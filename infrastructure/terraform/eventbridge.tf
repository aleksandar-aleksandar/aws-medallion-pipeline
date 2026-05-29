resource "aws_cloudwatch_event_rule" "hn_bronze_schedule" {
  name                = "${local.name_prefix}-hn-bronze-daily"
  description         = "Daily bronze ingest of previous day's Hacker News data"
  schedule_expression = var.hn_ingest_schedule
}

resource "aws_cloudwatch_event_target" "hn_bronze_schedule" {
  rule      = aws_cloudwatch_event_rule.hn_bronze_schedule.name
  target_id = "hn-bronze-ingest"
  arn       = aws_lambda_function.hn_bronze_ingest.arn
}
