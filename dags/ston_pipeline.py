from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from datetime import datetime
import requests
import json

default_args = {
    "owner": "ston-monitor",
}


def extract(**context):
    dex_response = requests.get("https://api.ston.fi/v1/stats/dex")
    dex = dex_response.json()
    pools_response = requests.post(
        "https://api.ston.fi/v1/pools/query", json={"sort_by": "tvl", "limit": 20}
    )
    pools = pools_response.json()
    context["ti"].xcom_push(key="raw_dex", value=dex)
    context["ti"].xcom_push(
        key="raw_pools", value=pools["pools"] if "pools" in pools else []
    )


def transform(**context):
    dex = context["ti"].xcom_pull(key="raw_dex")
    pools = context["ti"].xcom_pull(key="raw_pools")
    captured_at = datetime.utcnow()

    # Transform dex_stats (adjust keys/units after API inspection)
    dex_stats = {
        "captured_at": captured_at,
        "tvl_usd": float(dex.get("tvl", 0)) / 1e9,  # nano-units?
        "volume_24h": float(dex.get("volume_24h", 0)) / 1e9,
        "trades_24h": int(dex.get("trades_24h", 0)),
        "users_24h": int(dex.get("users_24h", 0)),
    }

    pool_snapshots = []
    for rank, pool in enumerate(pools, 1):
        pool_snapshots.append(
            {
                "captured_at": captured_at,
                "pool_address": pool.get("address"),
                "token_a": pool.get("token_a_address"),
                "token_b": pool.get("token_b_address"),
                "tvl_usd": float(pool.get("tvl", 0)) / 1e9,
                "volume_24h": float(pool.get("volume_24h", 0)) / 1e9,
                "apy": float(pool.get("apy", 0)),
                "rank": rank,
            }
        )

    context["ti"].xcom_push(key="dex_stats", value=[dex_stats])
    context["ti"].xcom_push(key="pool_snapshots", value=pool_snapshots)


def load(**context):
    dex_stats = context["ti"].xcom_pull(key="dex_stats")
    pool_snapshots = context["ti"].xcom_pull(key="pool_snapshots")

    hook = PostgresHook(
        postgres_conn_id="postgres_default"
    )  # Uses AIRFLOW__DATABASE__SQL_ALCHEMY_CONN
    hook.insert_rows(table="dex_stats", rows=dex_stats)
    hook.insert_rows(table="pool_snapshots", rows=pool_snapshots)


with DAG(
    dag_id="ston_pipeline",
    default_args=default_args,
    schedule_interval="@hourly",
    start_date=datetime(2026, 4, 15),
    catchup=False,
    tags=["stonfi"],
) as dag:
    extract_task = PythonOperator(task_id="extract", python_callable=extract)
    transform_task = PythonOperator(task_id="transform", python_callable=transform)
    load_task = PythonOperator(task_id="load", python_callable=load)

    extract_task >> transform_task >> load_task
