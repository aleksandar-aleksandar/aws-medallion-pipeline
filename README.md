# AWS Medallion Pipeline — Social Media Data Lake

Course project: collect, normalize, transform, and visualize data from **Hacker News** and **X (Twitter)** on AWS using **Medallion architecture** (bronze → silver → gold).

## Bronze layer (implemented)

| Source        | Mechanism                                      | S3 path                                      |
|---------------|------------------------------------------------|----------------------------------------------|
| Hacker News   | Lambda (daily) → Algolia API, raw JSON pages   | `bronze/hackernews/content_date=YYYY-MM-DD/` |
| X (Twitter)   | Manual upload of static dataset (raw, unchanged) | `bronze/x/dataset=<name>/raw/`             |

**Bronze rules:** no flattening, no HTML cleanup, no schema changes — only raw landing in S3.

## Silver layer (implemented)

| Input | Output | Mechanism |
|-------|--------|-----------|
| HN bronze JSON pages | `silver/users/` (partition `platform_partition`) | Lambda + awswrangler |
| X bronze CSV (tweet schema) | `silver/posts/` (partition `year/month/day`) | same Lambda |

**Tables:** `users` (`user_id`, `username`, `platform`, `karma_score`, `follower_count`, `is_verified`, `created_at`) and `posts` (`post_id`, `author_username`, `content_text`, `created_at`, `post_type`, `platform`, plus flattened HN refs).

**Normalization:** HTML strip, UTC timestamps, dedupe, nested HN `kids`/`children`/`parts` flattened to `child_ids`.

**Schedule:** EventBridge daily **02:30 UTC** (after bronze at 01:05 UTC).

**Manual invoke:**

```powershell
.\scripts\invoke_silver.ps1
.\scripts\invoke_silver.ps1 -ContentDate "2026-05-28"
.\scripts\invoke_silver.ps1 -NoX   # HN only
```

**Local test** (download bronze first or use `--s3`):

```powershell
py scripts\silver_normalize_local.py --s3 --bucket social-medias-dev-datalake-263112802384 --date 2026-05-28
```

Verify:

```powershell
aws s3 ls s3://<bucket>/silver/ --recursive
```

## Gold layer (implemented)

Reads silver Parquet, computes spec metrics/KPIs, writes partitioned gold tables under `gold/`.

| Gold table | What it contains |
|------------|------------------|
| `daily_hn_post_counts` | Per-day counts: story, ask, comment, job, poll |
| `daily_active_users` | Distinct active authors per platform per day |
| `daily_users_metric` | `total_users`, `new_users` per platform per day |
| `top_x_users_by_followers` | Top 10 X users by `follower_count` |
| `top_hn_users_by_karma_high` / `_low` | Top/bottom 10 HN users (karma from HN API) |
| `top_hn_jobs_by_score` | Top 10 HN jobs by `points` |
| `top_hn_posts_by_score` | Top 10 HN stories/asks/polls by `points` |
| `data_quality_score` | % non-null cells in silver `users` + `posts` |

**Schedule:** EventBridge daily **03:00 UTC** (after silver).

**Manual invoke:**

```powershell
.\scripts\invoke_gold.ps1
.\scripts\invoke_gold.ps1 -MetricDate "2026-05-28"
```

Verify:

```powershell
aws s3 ls s3://<bucket>/gold/ --recursive
```

## Visualization (implemented)

| Component | Role |
|-----------|------|
| EC2 + Docker | PostgreSQL + Apache Superset |
| `gold-to-postgres` Lambda | Loads gold Parquet → Postgres (`gold` schema) |
| Superset | Charts from Postgres tables |

**After deploy**, wait ~10 min for Docker bootstrap, then:

```powershell
.\scripts\invoke_gold_load.ps1
terraform -chdir=infrastructure\terraform output superset_url
terraform -chdir=infrastructure\terraform output -raw superset_admin_password
```

Setup guide: [docs/SUPERSET.md](docs/SUPERSET.md)

## Notifications (implemented)

CloudWatch alarms on all pipeline Lambdas → SNS → Discord webhook when **Errors > 0**.

1. Add webhook to `infrastructure/terraform/terraform.tfvars`:
   ```hcl
   discord_webhook_url = "https://discord.com/api/webhooks/..."
   ```
2. `terraform apply`
3. Test: `.\scripts\test_discord_notify.ps1`

Monitored Lambdas: bronze HN, silver, gold, gold-to-postgres.

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
lambdas/silver_normalize/     # Silver normalize Lambda (Python + awswrangler layer)
lambdas/gold_transform/       # Gold metrics Lambda (Python + awswrangler layer)
lambdas/gold_to_postgres/     # Gold S3 → PostgreSQL load Lambda
infrastructure/ec2/           # Docker Compose for Superset + Postgres
infrastructure/terraform/     # IaC: VPC, S3, Lambda, EventBridge, EC2
scripts/                      # invoke, upload, local test helpers
docs/SUPERSET.md              # Superset connection + chart guide
data/x/raw/                   # place Twitter datasets before upload
project_spec.md               # full assignment
```

## Next steps (not yet implemented)

_All major spec sections are implemented. Optional polish: tighten `superset_allowed_cidr` to your IP, stop EC2 when not demoing._
