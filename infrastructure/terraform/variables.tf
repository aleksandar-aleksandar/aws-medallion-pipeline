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
