output "data_lake_bucket_name" {
  description = "S3 data lake bucket (bronze/silver/gold prefixes)"
  value       = aws_s3_bucket.data_lake.id
}

output "data_lake_bucket_arn" {
  value = aws_s3_bucket.data_lake.arn
}

output "hn_bronze_lambda_name" {
  value = aws_lambda_function.hn_bronze_ingest.function_name
}

output "hn_bronze_lambda_arn" {
  value = aws_lambda_function.hn_bronze_ingest.arn
}

output "vpc_id" {
  value = aws_vpc.main.id
}

output "bronze_hackernews_prefix" {
  value = "s3://${aws_s3_bucket.data_lake.id}/bronze/hackernews/"
}

output "bronze_x_prefix" {
  value = "s3://${aws_s3_bucket.data_lake.id}/bronze/x/"
}

output "silver_normalize_lambda_name" {
  value = aws_lambda_function.silver_normalize.function_name
}

output "silver_normalize_lambda_arn" {
  value = aws_lambda_function.silver_normalize.arn
}

output "silver_prefix" {
  value = "s3://${aws_s3_bucket.data_lake.id}/silver/"
}

output "gold_transform_lambda_name" {
  value = aws_lambda_function.gold_transform.function_name
}

output "gold_transform_lambda_arn" {
  value = aws_lambda_function.gold_transform.arn
}

output "gold_prefix" {
  value = "s3://${aws_s3_bucket.data_lake.id}/gold/"
}

output "gold_to_postgres_lambda_name" {
  value = aws_lambda_function.gold_to_postgres.function_name
}

output "analytics_ec2_public_ip" {
  value = aws_eip.analytics.public_ip
}

output "superset_url" {
  value = "http://${aws_eip.analytics.public_ip}:8088"
}

output "superset_admin_user" {
  value = "admin"
}

output "superset_admin_password" {
  value     = local.superset_admin_password
  sensitive = true
}

output "postgres_host" {
  value = aws_instance.analytics.private_ip
}

output "postgres_password" {
  value     = local.postgres_password
  sensitive = true
}

output "pipeline_alerts_topic_arn" {
  value = try(aws_sns_topic.pipeline_alerts[0].arn, null)
}

output "discord_notify_lambda_name" {
  value = try(aws_lambda_function.discord_notify[0].function_name, null)
}
