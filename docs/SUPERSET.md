# Superset setup (after `terraform apply`)

## URLs and credentials

```powershell
terraform -chdir=infrastructure\terraform output superset_url
terraform -chdir=infrastructure\terraform output -raw superset_admin_password
terraform -chdir=infrastructure\terraform output superset_admin_user
```

- **URL:** `http://<eip>:8088`
- **User:** `admin`
- **Password:** from terraform output (default `MedallionAdmin123!` unless overridden)

Wait **5–10 minutes** after first `terraform apply` for Docker to pull images and start containers.

## Load gold data into Postgres

```powershell
.\scripts\invoke_gold_load.ps1
```

Tables land in schema **`gold`** (e.g. `gold.daily_hn_post_counts`).

## Connect Superset to metrics tables

1. Open Superset → **Settings** → **Database Connections** → **+ Database**
2. Select **PostgreSQL**
3. SQLAlchemy URI (from inside the Superset container, host is `postgres`):

   ```text
   postgresql+psycopg2://medallion:<postgres_password>@postgres:5432/medallion
   ```

   Get `<postgres_password>`:

   ```powershell
   terraform -chdir=infrastructure\terraform output -raw postgres_password
   ```

4. **Test connection** → **Connect**
5. **Data** → **Datasets** → **+ Dataset** → pick the DB → schema **`gold`** → choose a table

## Suggested charts

| Dataset | Chart type | Notes |
|---------|------------|-------|
| `daily_hn_post_counts` | Bar | `post_type` vs `post_count`, filter `date` |
| `daily_active_users` | Line | `date` vs `active_users`, series `platform` |
| `daily_users_metric` | Line | `new_users` / `total_users` over `date` |
| `top_x_users_by_followers` | Table | sort by `rank` |
| `data_quality_score` | Big number | `quality_score_pct` where `table_name=overall` |

## Troubleshooting

- **Superset not loading:** EC2 still bootstrapping — check via SSM Session Manager or wait longer.
- **Empty datasets:** run `.\scripts\invoke_gold_load.ps1` after gold transform.
- **Stop EC2 to save money:** AWS Console → EC2 → stop instance (EIP stays; Superset offline until started).
