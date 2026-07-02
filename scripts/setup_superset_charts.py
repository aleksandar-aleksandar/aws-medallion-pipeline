#!/usr/bin/env python3
"""Create or update Superset datasets and charts matching project spec."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from typing import Any
from urllib.parse import urljoin

GOLD_TABLES: tuple[str, ...] = (
    "daily_hn_post_counts",
    "daily_active_users",
    "daily_users_metric",
    "top_x_users_by_followers",
    "top_hn_users_by_karma_high",
    "top_hn_users_by_karma_low",
    "top_hn_jobs_by_score",
    "top_hn_posts_by_score",
    "data_quality_score",
)

SQL_DATASETS: dict[str, str] = {
  # Only dates with real HN activity (drops empty 2023 rows from X-only gold runs).
    "v_hn_post_counts_daily": """
        SELECT d.date::date AS date, d.post_type, d.post_count::bigint AS post_count
        FROM gold.daily_hn_post_counts d
        WHERE d.date::date IN (
            SELECT date::date
            FROM gold.daily_hn_post_counts
            GROUP BY date::date
            HAVING SUM(post_count) > 0
        )
        ORDER BY date, post_type
    """,
    "v_hn_active_users_daily": """
        SELECT date::date AS date, active_users::bigint AS active_users
        FROM gold.daily_active_users
        WHERE platform = 'Hacker News'
          AND active_users > 0
        ORDER BY date
    """,
    "v_x_active_users_daily": """
        SELECT date::date AS date, active_users::bigint AS active_users
        FROM gold.daily_active_users
        WHERE platform = 'X'
          AND active_users > 0
        ORDER BY date
    """,
}


def _metric(column: str, agg: str = "SUM", label: str | None = None) -> dict[str, Any]:
    return {
        "expressionType": "SIMPLE",
        "column": {"column_name": column},
        "aggregate": agg,
        "label": label or f"{agg}({column})",
    }


def _filter(column: str, op: str, value: str) -> dict[str, Any]:
    return {
        "clause": "WHERE",
        "expressionType": "SIMPLE",
        "subject": column,
        "operator": op,
        "comparator": value,
    }


# Charts aligned with project specification (section 4).
CHARTS: list[dict[str, Any]] = [
    {
        "slice_name": "HN Daily Post Counts by Type",
        "viz_type": "echarts_timeseries_line",
        "dataset": "v_hn_post_counts_daily",
        "params": {
            "x_axis": "date",
            "time_grain_sqla": "P1D",
            "metrics": [_metric("post_count", "SUM")],
            "groupby": ["post_type"],
            "row_limit": 10000,
            "show_legend": True,
            "rich_tooltip": True,
        },
    },
    {
        "slice_name": "HN Active Users (Daily)",
        "viz_type": "echarts_timeseries_line",
        "dataset": "v_hn_active_users_daily",
        "params": {
            "x_axis": "date",
            "time_grain_sqla": "P1D",
            "metrics": [_metric("active_users", "MAX")],
            "row_limit": 1000,
            "show_legend": False,
        },
    },
    {
        "slice_name": "X Active Users (Daily)",
        "viz_type": "echarts_timeseries_line",
        "dataset": "v_x_active_users_daily",
        "params": {
            "x_axis": "date",
            "time_grain_sqla": "P1D",
            "metrics": [_metric("active_users", "MAX")],
            "row_limit": 1000,
            "show_legend": False,
        },
    },
    {
        "slice_name": "Top 10 X Users by Followers",
        "viz_type": "table",
        "dataset": "top_x_users_by_followers",
        "params": {
            "all_columns": ["rank", "username", "follower_count", "is_verified", "date"],
            "order_by_cols": ["[\"rank\", true]"],
            "row_limit": 10,
        },
    },
    {
        "slice_name": "Top 10 HN Users by Karma (Highest)",
        "viz_type": "table",
        "dataset": "top_hn_users_by_karma_high",
        "params": {
            "all_columns": ["rank", "username", "karma_score"],
            "order_by_cols": ["[\"rank\", true]"],
            "row_limit": 10,
        },
    },
    {
        "slice_name": "Top 10 HN Users by Karma (Lowest)",
        "viz_type": "table",
        "dataset": "top_hn_users_by_karma_low",
        "params": {
            "all_columns": ["rank", "username", "karma_score"],
            "order_by_cols": ["[\"rank\", true]"],
            "row_limit": 10,
        },
    },
    {
        "slice_name": "Top 10 HN Jobs by Score",
        "viz_type": "table",
        "dataset": "top_hn_jobs_by_score",
        "params": {
            "all_columns": ["rank", "author_username", "content_text", "points", "date"],
            "order_by_cols": ["[\"rank\", true]"],
            "row_limit": 10,
        },
    },
    {
        "slice_name": "Top 10 HN Posts by Score",
        "viz_type": "table",
        "dataset": "top_hn_posts_by_score",
        "params": {
            "all_columns": ["rank", "post_type", "author_username", "points", "content_text", "date"],
            "order_by_cols": ["[\"rank\", true]"],
            "row_limit": 10,
        },
    },
    {
        "slice_name": "Data Quality Score (Overall)",
        "viz_type": "big_number_total",
        "dataset": "data_quality_score",
        "params": {
            "metric": _metric("quality_score_pct", "MAX"),
            "adhoc_filters": [_filter("table_name", "==", "overall")],
        },
    },
]

OBSOLETE_CHARTS: frozenset[str] = frozenset(
    {
        "Active Users Over Time",
        "Daily New Users by Platform",
        "Daily Users Metric by Platform",
    }
)


def _chart_params(datasource_id: int, params: dict[str, Any]) -> dict[str, Any]:
    """Superset explore requires datasource embedded in params JSON."""
    out = dict(params)
    out["datasource"] = f"{datasource_id}__table"
    return out


class SupersetClient:
    def __init__(self, base_url: str, username: str, password: str) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.username = username
        self.password = password
        self._jar = CookieJar()
        self._token: str | None = None
        self._csrf: str | None = None

    def _open(self, path: str, *, method: str = "GET", data: dict | None = None) -> Any:
        url = urljoin(self.base_url, path.lstrip("/"))
        body = None
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        if self._csrf and method != "GET":
            headers["X-CSRFToken"] = self._csrf
            headers["Referer"] = self.base_url
        if data is not None:
            body = json.dumps(data).encode()
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self._jar))
        try:
            with opener.open(req, timeout=60) as resp:
                raw = resp.read().decode()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode()
            raise RuntimeError(f"{method} {path} -> {exc.code}: {detail}") from exc

    def login(self) -> None:
        payload = {
            "username": self.username,
            "password": self.password,
            "provider": "db",
            "refresh": True,
        }
        result = self._open("api/v1/security/login", method="POST", data=payload)
        self._token = result["access_token"]
        csrf = self._open("api/v1/security/csrf_token/")
        self._csrf = csrf["result"]

    def list_databases(self) -> list[dict[str, Any]]:
        return self._open("api/v1/database/")["result"]

    def list_datasets(self) -> list[dict[str, Any]]:
        return self._open("api/v1/dataset/?q=(page:0,page_size:200)")["result"]

    def list_charts(self) -> list[dict[str, Any]]:
        return self._open("api/v1/chart/?q=(page:0,page_size:200)")["result"]

    def create_physical_dataset(self, database_id: int, schema: str, table_name: str) -> dict[str, Any]:
        payload = {"database": database_id, "schema": schema, "table_name": table_name}
        return self._open("api/v1/dataset/", method="POST", data=payload)

    def delete_dataset(self, dataset_id: int) -> None:
        self._open(f"api/v1/dataset/{dataset_id}", method="DELETE")

    def refresh_dataset(self, dataset_id: int) -> None:
        try:
            self._open(f"api/v1/dataset/{dataset_id}/refresh", method="POST", data={})
        except RuntimeError as exc:
            print(f"  warn: refresh dataset {dataset_id} failed: {exc}")

    def create_sql_dataset(self, database_id: int, table_name: str, sql: str) -> dict[str, Any]:
        payload = {"database": database_id, "table_name": table_name, "sql": sql.strip()}
        return self._open("api/v1/dataset/", method="POST", data=payload)

    def update_sql_dataset(self, dataset_id: int, database_id: int, table_name: str, sql: str) -> None:
        payload = {"database_id": database_id, "table_name": table_name, "sql": sql.strip()}
        self._open(f"api/v1/dataset/{dataset_id}", method="PUT", data=payload)

    def delete_chart(self, chart_id: int) -> None:
        self._open(f"api/v1/chart/{chart_id}", method="DELETE")

    def create_chart(
        self,
        *,
        slice_name: str,
        viz_type: str,
        datasource_id: int,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        payload = {
            "slice_name": slice_name,
            "viz_type": viz_type,
            "datasource_id": datasource_id,
            "datasource_type": "table",
            "params": json.dumps(_chart_params(datasource_id, params)),
        }
        return self._open("api/v1/chart/", method="POST", data=payload)

    def update_chart(
        self,
        chart_id: int,
        *,
        slice_name: str,
        viz_type: str,
        datasource_id: int,
        params: dict[str, Any],
    ) -> None:
        payload = {
            "slice_name": slice_name,
            "viz_type": viz_type,
            "datasource_id": datasource_id,
            "datasource_type": "table",
            "params": json.dumps(_chart_params(datasource_id, params)),
        }
        self._open(f"api/v1/chart/{chart_id}", method="PUT", data=payload)


def terraform_output(name: str, terraform_dir: str) -> str:
    result = subprocess.run(
        ["terraform", f"-chdir={terraform_dir}", "output", "-raw", name],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def ensure_datasets(client: SupersetClient, database_id: int, *, update: bool) -> dict[str, int]:
    existing = {d.get("table_name"): d["id"] for d in client.list_datasets()}
    ids: dict[str, int] = {}

    for table in GOLD_TABLES:
        if table in existing:
            ds_id = existing[table]
            meta = client._open(f"api/v1/dataset/{ds_id}")["result"]
            if not meta.get("columns") and table.startswith("top_hn_users_by_karma"):
                client.delete_dataset(ds_id)
                print(f"  recreating stale dataset gold.{table}")
                created = client.create_physical_dataset(database_id, "gold", table)
                ids[table] = created["id"]
                continue
            ids[table] = ds_id
            print(f"  dataset exists: gold.{table} (id={ids[table]})")
            continue
        try:
            created = client.create_physical_dataset(database_id, "gold", table)
        except RuntimeError as exc:
            print(f"  skipped dataset gold.{table}: {exc}")
            continue
        ids[table] = created["id"]
        print(f"  created dataset: gold.{table} (id={ids[table]})")

    for name, sql in SQL_DATASETS.items():
        if name in existing:
            ds_id = existing[name]
            if update:
                try:
                    client.update_sql_dataset(ds_id, database_id, name, sql)
                    print(f"  updated sql dataset: {name} (id={ds_id})")
                except RuntimeError as exc:
                    client.delete_dataset(ds_id)
                    created = client.create_sql_dataset(database_id, name, sql)
                    ds_id = created["id"]
                    print(f"  recreated sql dataset: {name} (id={ds_id})")
            else:
                print(f"  sql dataset exists: {name} (id={ds_id})")
            ids[name] = ds_id
            continue
        try:
            created = client.create_sql_dataset(database_id, name, sql)
        except RuntimeError as exc:
            print(f"  skipped sql dataset {name}: {exc}")
            continue
        ids[name] = created["id"]
        print(f"  created sql dataset: {name} (id={ids[name]})")

    return ids


def ensure_charts(client: SupersetClient, dataset_ids: dict[str, int], *, update: bool) -> None:
    existing_by_name = {c["slice_name"]: c for c in client.list_charts()}

    for obsolete in OBSOLETE_CHARTS:
        if obsolete in existing_by_name:
            chart_id = existing_by_name[obsolete]["id"]
            client.delete_chart(chart_id)
            print(f"  deleted obsolete chart: {obsolete}")
            del existing_by_name[obsolete]

    for spec in CHARTS:
        name = spec["slice_name"]
        dataset = spec["dataset"]
        if dataset not in dataset_ids:
            print(f"  skipped chart {name}: dataset {dataset} not available")
            continue
        ds_id = dataset_ids[dataset]
        if name in existing_by_name:
            if not update:
                print(f"  chart exists: {name}")
                continue
            chart_id = existing_by_name[name]["id"]
            client.update_chart(
                chart_id,
                slice_name=name,
                viz_type=spec["viz_type"],
                datasource_id=ds_id,
                params=spec["params"],
            )
            print(f"  updated chart: {name}")
            continue
        client.create_chart(
            slice_name=name,
            viz_type=spec["viz_type"],
            datasource_id=ds_id,
            params=spec["params"],
        )
        print(f"  created chart: {name}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or update Superset datasets and charts")
    parser.add_argument("--url", help="Superset base URL (default: terraform output)")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", help="Superset admin password (default: terraform output)")
    parser.add_argument("--database-id", type=int, help="Superset database id (default: first DB)")
    parser.add_argument("--update", action="store_true", help="Update existing charts in place")
    parser.add_argument(
        "--terraform-dir",
        default=str((__import__("pathlib").Path(__file__).resolve().parents[1] / "infrastructure" / "terraform")),
    )
    args = parser.parse_args()

    url = args.url or terraform_output("superset_url", args.terraform_dir)
    password = args.password or terraform_output("superset_admin_password", args.terraform_dir)

    print(f"Connecting to {url} ...")
    client = SupersetClient(url, args.username, password)
    client.login()

    databases = client.list_databases()
    if not databases:
        print("No database connections in Superset. Add PostgreSQL in UI first.", file=sys.stderr)
        return 1
    database_id = args.database_id or databases[0]["id"]
    print(f"Using database id={database_id} ({databases[0]['database_name']})")

    print("Ensuring datasets ...")
    dataset_ids = ensure_datasets(client, database_id, update=args.update)
    if not dataset_ids:
        print("\nNo datasets found. Run first:\n  .\\scripts\\invoke_gold_load.ps1", file=sys.stderr)
        return 1

    print("Ensuring charts ...")
    ensure_charts(client, dataset_ids, update=args.update)

    print(f"\nDone. Open {url} -> Charts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
