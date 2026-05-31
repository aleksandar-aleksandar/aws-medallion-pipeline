# command cheat sheet

Key → command. Run from repo root unless noted.

**Repo root:** `c:\Users\MyPC\Desktop\aws-medallion-pipeline`

---

## Setup & verify AWS

| Key | Command |
|-----|---------|
| Go to repo root | `cd c:\Users\MyPC\Desktop\aws-medallion-pipeline` |
| Check AWS login works | `aws sts get-caller-identity` |
| Check AWS CLI version | `aws --version` |
| Check Terraform version | `terraform version` |
| Check Python (local test) | `py --version` |

---

## Terraform (infrastructure)

| Key | Command |
|-----|---------|
| Go to Terraform folder | `cd infrastructure\terraform` |
| First-time setup (providers) | `terraform init` |
| Preview changes (safe, no changes) | `terraform plan` |
| Deploy / update infrastructure | `terraform apply` |
| Show bucket name, Lambda name, etc. | `terraform output` |
| Bucket name only | `terraform output -raw data_lake_bucket_name` |
| Lambda name only | `terraform output -raw hn_bronze_lambda_name` |
| Tear down everything (save cost) | `terraform destroy` |

---

## S3 — prove bronze data exists

| Key | Command |
|-----|---------|
| List HN bronze (first 20 lines) | `aws s3 ls "s3://social-medias-dev-datalake-263112802384/bronze/hackernews/" --recursive \| Select-Object -First 20` |
| List all HN bronze | `aws s3 ls "s3://social-medias-dev-datalake-263112802384/bronze/hackernews/" --recursive` |
| List X (Twitter) bronze | `aws s3 ls "s3://social-medias-dev-datalake-263112802384/bronze/x/" --recursive` |
| List one HN date folder | `aws s3 ls "s3://social-medias-dev-datalake-263112802384/bronze/hackernews/content_date=2026-05-28/"` |
| Print manifest to terminal | `aws s3 cp "s3://social-medias-dev-datalake-263112802384/bronze/hackernews/content_date=2026-05-28/manifest.json" -` |
| Bucket name from Terraform (dynamic) | `$bucket = terraform -chdir=infrastructure\terraform output -raw data_lake_bucket_name` |
| List HN with dynamic bucket | `aws s3 ls "s3://$bucket/bronze/hackernews/" --recursive` |

---

## Hacker News — manual ingest (optional live demo)

| Key | Command |
|-----|---------|
| Ingest yesterday (UTC) | `.\scripts\invoke_hn_bronze.ps1` |
| Ingest specific date | `.\scripts\invoke_hn_bronze.ps1 -ContentDate "2026-05-28"` |
| Lambda logs hint (after invoke) | CloudWatch → `/aws/lambda/social-medias-dev-hn-bronze-ingest` |

**Note:** Scheduled run is daily **01:05 UTC** (no laptop needed). Manual invoke is only for demo.

---

## X (Twitter) — upload bronze CSV

| Key | Command |
|-----|---------|
| Create local folder for CSVs | `mkdir data\x\raw` |
| Upload covid tweets | `.\scripts\upload_x_bronze.ps1 -DatasetName "covid-tweets" -LocalFile "data\x\raw\tweets.csv"` |
| Upload bitcoin tweets | `.\scripts\upload_x_bronze.ps1 -DatasetName "bitcoin-tweets" -LocalFile "data\x\raw\Bitcoin_tweets_dataset_2.csv"` |
| Raw S3 upload (no script) | `aws s3 cp "data\x\raw\tweets.csv" "s3://social-medias-dev-datalake-263112802384/bronze/x/dataset=covid-tweets/raw/tweets.csv"` |

**Note:** Already uploaded if `aws s3 ls .../bronze/x/` shows both datasets. Re-upload only for live demo.

---

## Local test (no AWS)

| Key | Command |
|-----|---------|
| Smoke test — yesterday, story tag | `py scripts\test_hn_fetch.py` |
| Smoke test — specific date | `py scripts\test_hn_fetch.py --date 2026-05-28 --tag story` |
| Smoke test — all HN types | `py scripts\test_hn_fetch.py --date 2026-05-28 --tag all` |

---

## Flow 

| Step | Key | Command |
|------|-----|---------|
| 1 | Repo root | `cd c:\Users\MyPC\Desktop\aws-medallion-pipeline` |
| 2 | AWS OK | `aws sts get-caller-identity` |
| 3 | Show outputs | `terraform -chdir=infrastructure\terraform output` |
| 4 | Show HN data | `aws s3 ls "s3://social-medias-dev-datalake-263112802384/bronze/hackernews/" --recursive \| Select-Object -First 20` |
| 5 | Show X data | `aws s3 ls "s3://social-medias-dev-datalake-263112802384/bronze/x/" --recursive` |
| 6 | Optional live HN | `.\scripts\invoke_hn_bronze.ps1 -ContentDate "2026-05-28"` |

---

## Quick reference — resource names

| Key | Value |
|-----|-------|
| S3 bucket | `social-medias-dev-datalake-263112802384` |
| Lambda function | `social-medias-dev-hn-bronze-ingest` |
| AWS region | `eu-central-1` |
| HN bronze prefix | `s3://social-medias-dev-datalake-263112802384/bronze/hackernews/` |
| X bronze prefix | `s3://social-medias-dev-datalake-263112802384/bronze/x/` |
| EventBridge schedule | Daily 01:05 UTC — ingests previous UTC day |

