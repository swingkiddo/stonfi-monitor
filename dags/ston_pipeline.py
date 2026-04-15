from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from datetime import datetime, timezone
import requests
import psycopg2

default_args = {
    "owner": "ston-monitor",
}


def extract(**context):
    dex = requests.get("https://api.ston.fi/v1/stats/dex", timeout=30).json()

    all_pools = requests.get("https://api.ston.fi/v1/pools", timeout=60).json()
    pool_list = all_pools.get("pool_list", [])
    top20 = sorted(
        pool_list,
        key=lambda x: float(x.get("lp_total_supply_usd", 0) or 0),
        reverse=True,
    )[:20]

    print(
        f"Extract: dex keys={list(dex.keys())}, pools={len(pool_list)}, top20={len(top20)}"
    )

    context["ti"].xcom_push(key="raw_dex", value=dex)
    context["ti"].xcom_push(key="raw_top20", value=top20)


def transform(**context):
    # Забираем XCom явно с upstream-задачи extract.
    # В разных версиях/настройках Airflow поведение xcom_pull без task_ids может отличаться.
    dex = context["ti"].xcom_pull(task_ids="extract", key="raw_dex")
    top20 = context["ti"].xcom_pull(task_ids="extract", key="raw_top20")
    captured_at = datetime.now(timezone.utc).isoformat()

    if not dex or not top20:
        raise ValueError(
            f"Empty XCom: dex={dex is not None}, pools={top20 is not None}"
        )

    stats = dex.get("stats", {}) if isinstance(dex, dict) else {}

    dex_stats = {
        "captured_at": captured_at,
        "tvl_usd": float(stats.get("tvl", 0)),
        "volume_24h": float(stats.get("volume_usd", 0)),
        "trades_24h": int(stats.get("trades", 0)),
        "users_24h": int(stats.get("unique_wallets", 0)),
    }

    pool_snapshots = []
    for rank, pool in enumerate(top20, 1):
        pool_snapshots.append(
            {
                "captured_at": captured_at,
                "pool_address": pool.get("address"),
                "token_a": pool.get("token0_address"),
                "token_b": pool.get("token1_address"),
                "tvl_usd": float(pool.get("lp_total_supply_usd", 0)),
                "volume_24h": float(pool.get("volume_24h_usd", 0)),
                "apy": float(pool.get("apy_1d", 0) or 0),
                "rank": rank,
            }
        )

    print(f"Transform: dex_stats={dex_stats}, pools={len(pool_snapshots)}")

    context["ti"].xcom_push(key="dex_stats", value=[dex_stats])
    context["ti"].xcom_push(key="pool_snapshots", value=pool_snapshots)


def load(**context):
    # Аналогично transform: явно указываем task_ids.
    dex_stats = context["ti"].xcom_pull(task_ids="transform", key="dex_stats")
    pool_snapshots = context["ti"].xcom_pull(task_ids="transform", key="pool_snapshots")

    if not dex_stats or not pool_snapshots:
        raise ValueError(f"Empty data! dex={dex_stats}, pools={pool_snapshots}")

    print(f"Load: dex={dex_stats}, pools={len(pool_snapshots)}")

    conn = psycopg2.connect(
        host="postgres", dbname="airflow", user="airflow", password="airflow"
    )
    cur = conn.cursor()

    for d in dex_stats:
        cur.execute(
            "INSERT INTO dex_stats (captured_at, tvl_usd, volume_24h, trades_24h, users_24h) VALUES (%s, %s, %s, %s, %s)",
            (
                d["captured_at"],
                d["tvl_usd"],
                d["volume_24h"],
                d["trades_24h"],
                d["users_24h"],
            ),
        )

    for p in pool_snapshots:
        cur.execute(
            "INSERT INTO pool_snapshots (captured_at, pool_address, token_a, token_b, tvl_usd, volume_24h, apy, rank) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                p["captured_at"],
                p["pool_address"],
                p["token_a"],
                p["token_b"],
                p["tvl_usd"],
                p["volume_24h"],
                p["apy"],
                p["rank"],
            ),
        )

    conn.commit()
    cur.close()
    conn.close()
    print(f"Load done: 1 dex row + {len(pool_snapshots)} pool rows")


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
