# AWS Medallion Pipeline — Social Media Data Lake

Course project: collect, normalize, transform, and visualize data from **Hacker News** and **X (Twitter)** on AWS using **Medallion architecture** (bronze → silver → gold).

## Bronze layer (implemented)

| Source        | Mechanism                                      | S3 path                                      |
|---------------|------------------------------------------------|----------------------------------------------|
| Hacker News   | Lambda (daily) → Algolia API, raw JSON pages   | `bronze/hackernews/content_date=YYYY-MM-DD/` |
| X (Twitter)   | Manual upload of static dataset (raw, unchanged) | `bronze/x/<dataset>/`                     |

**Bronze rules:** no flattening, no HTML cleanup, no schema changes — only raw landing in S3.

## Prerequisites

1. [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) configured (`aws sts get-caller-identity` works).
2. [Terraform](https://developer.hashicorp.com/terraform/install) >= 1.5.
3. AWS account with permissions for VPC, NAT Gateway, S3, Lambda, IAM, EventBridge.

> **Cost note:** NAT Gateway incurs hourly + data charges. Destroy the stack when not demoing: `terraform destroy`.

## Deploy infrastructure

```powershell
cd infrastructure\terraform
copy terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars if needed (region, project name)

terraform init
terraform plan
terraform apply
```

Save outputs:

```powershell
terraform output data_lake_bucket_name
terraform output hn_bronze_lambda_name
```

## Run Hacker News ingest

**Scheduled:** EventBridge runs daily at 01:05 UTC and ingests the **previous UTC calendar day**.

**Manual test** (after deploy):

```powershell
# from repo root
.\scripts\invoke_hn_bronze.ps1

# optional: specific date (for backfill / testing)
.\scripts\invoke_hn_bronze.ps1 -ContentDate "2026-05-27"
```

Verify objects:

```powershell
$bucket = terraform -chdir=infrastructure\terraform output -raw data_lake_bucket_name
aws s3 ls "s3://$bucket/bronze/hackernews/" --recursive
```

Expected layout:

```text
bronze/hackernews/content_date=2026-05-27/
├── story/page_0000.json
├── ask/page_0000.json
├── comment/page_0000.json
├── job/page_0000.json
├── poll/page_0000.json
└── manifest.json
```

## Upload X (Twitter) bronze data

1. Download a public dataset (e.g. [Covid Tweets](https://www.kaggle.com/datasets) or similar).
2. Place the raw file under `data/x/raw/` (not committed if large).
3. Upload unchanged:

```powershell
.\scripts\upload_x_bronze.ps1 -DatasetName "covid-tweets" -LocalFile "data\x\raw\tweets.csv"
```

Result: `s3://<bucket>/bronze/x/dataset=covid-tweets/raw/tweets.csv`

## Local test (no AWS)

Smoke-test Algolia queries for yesterday:

```powershell
python scripts\test_hn_fetch.py
python scripts\test_hn_fetch.py --date 2026-05-27 --tag story
```

## Project layout

```text
lambdas/hn_bronze_ingest/     # HN bronze Lambda (Python)
infrastructure/terraform/     # IaC: VPC, S3, Lambda, EventBridge
scripts/                      # invoke, upload, local test helpers
data/x/raw/                   # place Twitter datasets before upload
project-specification.md      # full assignment
```

## Next steps (not yet implemented)

- **Silver:** normalize to Parquet (`users`, `posts`), awswrangler, partitioning.
- **Gold:** daily metrics/KPIs, star schema.
- **Visualization:** Superset + PostgreSQL on EC2, load Lambda.
- **Notifications:** Discord on failed jobs.
