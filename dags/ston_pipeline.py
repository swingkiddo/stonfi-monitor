from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from datetime import datetime, timezone
import requests

default_args = {
    "owner": "ston-monitor",
}


def extract(**context):
    dex_response = requests.get("https://api.ston.fi/v1/stats/dex", timeout=30)
    dex_response.raise_for_status()
    dex = dex_response.json()

    pools_response = requests.get("https://api.ston.fi/v1/pools", timeout=30)
    pools_response.raise_for_status()
    pools = pools_response.json()

    context["ti"].xcom_push(key="raw_dex", value=dex)
    context["ti"].xcom_push(key="raw_pools", value=pools)


def transform(**context):
    dex = context["ti"].xcom_pull(key="raw_dex")
    pools_data = context["ti"].xcom_pull(key="raw_pools")
    pools = pools_data.get("pool_list", []) if isinstance(pools_data, dict) else []
    captured_at = datetime.now(timezone.utc)

    stats = dex.get("stats", {}) if isinstance(dex, dict) else {}

    dex_stats = {
        "captured_at": captured_at,
        "tvl_usd": float(stats.get("tvl", 0)),
        "volume_24h": float(stats.get("volume_usd", 0)),
        "trades_24h": int(stats.get("trades", 0)),
        "users_24h": int(stats.get("unique_wallets", 0)),
    }

    sorted_pools = sorted(
        pools, key=lambda x: float(x.get("tvl", 0) or 0), reverse=True
    )[:20]
    pool_snapshots = []
    for rank, pool in enumerate(sorted_pools, 1):
        pool_snapshots.append(
            {
                "captured_at": captured_at,
                "pool_address": pool.get("address"),
                "token_a": pool.get("token_a_address"),
                "token_b": pool.get("token_b_address"),
                "tvl_usd": float(pool.get("tvl", 0)),
                "volume_24h": float(pool.get("volume_24h", 0)),
                "apy": float(pool.get("apy", 0) or 0),
                "rank": rank,
            }
        )

    print("Transform pushing dex_stats:", [dex_stats])
    context["ti"].xcom_push(key="dex_stats", value=[dex_stats])
    context["ti"].xcom_push(key="pool_snapshots", value=pool_snapshots)


def load(**context):
    dex_stats = context["ti"].xcom_pull(key="dex_stats")
    pool_snapshots = context["ti"].xcom_pull(key="pool_snapshots")
    print("Load dex_stats:", dex_stats)
    print("Load pool_snapshots len:", len(pool_snapshots or []))

    hook = PostgresHook(postgres_conn_id="postgres_default")

    # Dex rows: captured_at, tvl_usd, volume_24h, trades_24h, users_24h
    if dex_stats:
        dex_rows = [
            [
                d["captured_at"],
                d["tvl_usd"],
                d["volume_24h"],
                d["trades_24h"],
                d["users_24h"],
            ]
            for d in dex_stats
        ]
        hook.insert_rows(table="dex_stats", rows=dex_rows)

    # Pools: captured_at, pool_address, token_a, token_b, tvl_usd, volume_24h, apy, rank
    if pool_snapshots:
        pool_rows = [
            [
                p["captured_at"],
                p["pool_address"],
                p["token_a"],
                p["token_b"],
                p["tvl_usd"],
                p["volume_24h"],
                p["apy"],
                p["rank"],
            ]
            for p in pool_snapshots
        ]
        hook.insert_rows(table="pool_snapshots", rows=pool_rows)


with DAG(
    dag_id="ston_pipeline",
    default_args=default_args,
    schedule="@hourly",
    start_date=datetime(2026, 4, 15),
    catchup=False,
    tags=["stonfi"],
) as dag:
    extract_task = PythonOperator(task_id="extract", python_callable=extract)
    transform_task = PythonOperator(task_id="transform", python_callable=transform)
    load_task = PythonOperator(task_id="load", python_callable=load)

    extract_task >> transform_task >> load_task
