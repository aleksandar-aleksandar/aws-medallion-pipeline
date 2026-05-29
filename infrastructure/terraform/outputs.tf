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
