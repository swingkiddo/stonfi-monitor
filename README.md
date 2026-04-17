# STON.fi Pool Monitor

ETL pipeline that pulls data from STON.fi DEX API every hour, stores it in PostgreSQL, and visualizes with Metabase dashboards.

## Architecture

```
STON.fi API → Airflow DAG → PostgreSQL → Metabase
```

## Quick Start

```bash
# Initialize and start all services
docker compose up airflow-init
docker compose up -d

# Open UIs
Airflow:   http://localhost:33101 (airflow / airflow)
Metabase:  http://localhost:33100
```

## Services

| Service | Port | Description |
|---------|------|-------------|
| Airflow API | 33101 | DAG orchestration |
| Metabase | 33100 | Dashboards |
| Flower | 5555 | Celery monitoring (optional, run with `--profile flower`) |

## Database Tables

- **dex_stats** — hourly DEX overview (TVL, volume, trades, users)
- **pool_snapshots** — hourly snapshots of top 20 pools (addresses, TVL, APY)

Connection (for Metabase):
- Host: `postgres`
- Port: `5432`
- Database: `airflow`
- User/Pass: `airflow`

## DAG: ston_pipeline

Runs hourly. Extracts data from STON.fi API, transforms, and loads into PostgreSQL.

## Verify Data

```bash
docker compose exec -T postgres psql -U airflow -d airflow -c "SELECT MAX(captured_at) FROM dex_stats;"
docker compose exec -T postgres psql -U airflow -d airflow -c "SELECT COUNT(*) FROM pool_snapshots;"
```

## Project Structure

```
├── docker-compose.yaml   # All services (Airflow, Postgres, Redis, Metabase)
├── dags/
│   └── ston_pipeline.py  # ETL DAG
├── init.sql              # Table definitions
├── config/               # Airflow config
├── logs/                 # Airflow logs
└── plugins/              # Airflow plugins
```
