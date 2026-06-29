variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "eu-central-1"
}

variable "project_name" {
  description = "Prefix for resource names"
  type        = string
  default     = "social-medias"
}

variable "environment" {
  description = "Environment label (dev, prod, ...)"
  type        = string
  default     = "dev"
}

variable "hn_ingest_schedule" {
  description = "EventBridge cron (UTC) — daily ingest of previous day's HN data"
  type        = string
  default     = "cron(5 1 * * ? *)" # 01:05 UTC
}

variable "hn_lambda_timeout" {
  description = "Lambda timeout in seconds (comments can be voluminous)"
  type        = number
  default     = 900
}

variable "hn_lambda_memory" {
  description = "Lambda memory in MB"
  type        = number
  default     = 512
}

variable "silver_normalize_schedule" {
  description = "EventBridge cron (UTC) — daily silver normalize after bronze"
  type        = string
  default     = "cron(30 2 * * ? *)" # 02:30 UTC
}

variable "silver_lambda_timeout" {
  description = "Silver Lambda timeout in seconds (large X CSV)"
  type        = number
  default     = 900
}

variable "silver_lambda_memory" {
  description = "Silver Lambda memory in MB"
  type        = number
  default     = 3008
}

variable "awswrangler_layer_arn" {
  description = "AWS SDK for pandas (awswrangler) Lambda layer ARN"
  type        = string
  default     = "arn:aws:lambda:eu-central-1:336392948345:layer:AWSSDKPandas-Python312:27"
}

variable "gold_transform_schedule" {
  description = "EventBridge cron (UTC) — daily gold transform after silver"
  type        = string
  default     = "cron(0 3 * * ? *)" # 03:00 UTC
}

variable "gold_lambda_timeout" {
  description = "Gold Lambda timeout in seconds"
  type        = number
  default     = 900
}

variable "gold_lambda_memory" {
  description = "Gold Lambda memory in MB (reads full silver dataset)"
  type        = number
  default     = 3008
}

variable "gold_load_schedule" {
  description = "EventBridge cron (UTC) — load gold into Postgres after gold transform"
  type        = string
  default     = "cron(30 3 * * ? *)" # 03:30 UTC
}

variable "gold_load_lambda_timeout" {
  description = "Gold load Lambda timeout in seconds"
  type        = number
  default     = 300
}

variable "gold_load_lambda_memory" {
  description = "Gold load Lambda memory in MB"
  type        = number
  default     = 1024
}

variable "analytics_instance_type" {
  description = "EC2 instance type for Superset + PostgreSQL (t3.micro for Free Tier accounts)"
  type        = string
  default     = "t3.micro"
}

variable "superset_allowed_cidr" {
  description = "CIDR allowed to reach Superset UI on port 8088 (restrict to your IP/32 for production)"
  type        = string
  default     = "0.0.0.0/0"
}

variable "postgres_password" {
  description = "Optional override for PostgreSQL password (random if empty)"
  type        = string
  default     = null
  sensitive   = true
}

variable "superset_admin_password" {
  description = "Superset admin UI password"
  type        = string
  default     = null
  sensitive   = true
}

variable "discord_webhook_url" {
  description = "Discord incoming webhook URL for pipeline failure alerts (leave empty to disable)"
  type        = string
  default     = ""
  sensitive   = true
}
