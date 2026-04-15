# STON.fi Pool Monitor — Development Plan

## Overview

We're building a local data stack: Airflow pulls data from the STON.fi API every hour, writes it to PostgreSQL, and Metabase renders a live dashboard. Everything spins up with a single docker-compose command.

```
STON.fi API → Airflow DAG → PostgreSQL → Metabase
```

---

## Phase 0 — Project Setup

Create the folder structure upfront — Airflow strictly looks for DAG files inside `dags/`.

```
ston-monitor/
├── docker-compose.yml
├── dags/
│   └── ston_pipeline.py
├── logs/
└── plugins/
```

---

## Phase 1 — Infrastructure ⭐️

**The most critical step.** Writing code before the infrastructure is running is pointless.

### 1.1 Write docker-compose.yml

We need 4 services:

- **postgres** — data storage. Holds both the STON.fi analytics tables and Airflow's internal database
- **redis** — required by Airflow as a task queue broker (just needs to exist, don't touch it)
- **airflow** — orchestrator, runs the DAG on schedule
- **metabase** — dashboard layer, reads from postgres

Start with the official Airflow compose file and add Metabase to it:

```bash
curl -LfO 'https://airflow.apache.org/docs/apache-airflow/stable/docker-compose.yaml'
```

Add the Metabase service at the bottom of the file:

```yaml
metabase:
  image: metabase/metabase:latest
  ports:
    - "3000:3000"
  environment:
    MB_DB_TYPE: postgres
    MB_DB_DBNAME: metabase
    MB_DB_PORT: 5432
    MB_DB_USER: airflow
    MB_DB_PASS: airflow
    MB_DB_HOST: postgres
  depends_on:
    - postgres
```

### 1.2 First Launch

```bash
# Initialization — run only once
docker compose up airflow-init

# Start the full stack
docker compose up -d
```

### 1.3 Verify Everything Is Alive

- Airflow: `http://localhost:8080` (login: airflow / airflow)
- Metabase: `http://localhost:3000`
- Postgres is healthy if Airflow UI loads successfully

---

## Phase 2 — Explore the STON.fi API

Before writing any ETL logic, understand what we're pulling and what the response format looks like.

### 2.1 Endpoints We Need

Open these in a browser or hit them with curl to inspect the raw responses.

**Overall DEX stats:**
```
GET https://api.ston.fi/v1/stats/dex
```
Returns: total TVL, 24h volume, trade count, unique users.

**Top pools:**
```
POST https://api.ston.fi/v1/pools/query
Body: {"sort_by": "tvl", "limit": 20}
```
Returns: pool list with TVL, volume, APY, token addresses.

### 2.2 Inspect the Raw Responses

```bash
curl https://api.ston.fi/v1/stats/dex | python3 -m json.tool
```

Pay attention to: which fields are useful, whether numbers come as strings, whether values are in nano-units (divide by 10⁹) or already in USD.

---

## Phase 3 — ETL DAG ⭐️

**The core of the project.** This is where the actual data engineering happens.

### 3.1 Create Tables in PostgreSQL

Two time-series tables so we can track trends over time.

```sql
-- One row per hour: overall DEX health
CREATE TABLE dex_stats (
    id          SERIAL PRIMARY KEY,
    captured_at TIMESTAMP DEFAULT NOW(),
    tvl_usd     NUMERIC,
    volume_24h  NUMERIC,
    trades_24h  INTEGER,
    users_24h   INTEGER
);

-- 20 rows per hour: snapshot of top pools
CREATE TABLE pool_snapshots (
    id           SERIAL PRIMARY KEY,
    captured_at  TIMESTAMP DEFAULT NOW(),
    pool_address TEXT,
    token_a      TEXT,
    token_b      TEXT,
    tvl_usd      NUMERIC,
    volume_24h   NUMERIC,
    apy          NUMERIC,
    rank         INTEGER  -- position in the top list at snapshot time
);
```

### 3.2 Write the DAG — dags/ston_pipeline.py

The DAG has three tasks that run strictly in sequence:

**Task 1 — extract:** make two HTTP requests to the STON.fi API, push the raw JSON into XCom (Airflow's built-in mechanism for passing data between tasks).

**Task 2 — transform:** pull data from XCom and clean it. Numbers come as strings — cast to float. Nano-units get divided by 10⁹. Keep only the fields we need. Attach `captured_at` timestamp.

**Task 3 — load:** receive the transformed data, connect to Postgres via psycopg2, INSERT into both tables.

```python
# Task execution order at the bottom of the file:
extract >> transform >> load
```

### 3.3 Configure the Schedule and Test It

In the DAG definition:

```python
schedule_interval='@hourly',
catchup=False,  # don't backfill missed runs on first start
```

Trigger it manually in the Airflow UI — hit **Trigger DAG**. All three circles should turn green in sequence. If one turns red — check **Logs**.

---

## Phase 4 — Metabase Dashboard ⭐️

Once the DAG has run at least 2–3 times and the tables have data — go build the dashboard.

### 4.1 Connect PostgreSQL as a Data Source

In Metabase: Settings → Databases → Add database → PostgreSQL.

Connection parameters:

```
Host:     postgres     ← not localhost! this is the Docker service name
Port:     5432
Database: airflow
Username: airflow
Password: airflow
```

### 4.2 Create Questions (Metabase's term for queries/widgets)

Each widget is a separate SQL query or a visual query builder result.

**TVL over time** — line chart:
```sql
SELECT captured_at, tvl_usd
FROM dex_stats
ORDER BY captured_at;
```

**Top 10 pools by TVL** — table (latest snapshot only):
```sql
SELECT token_a, token_b, tvl_usd, volume_24h, apy
FROM pool_snapshots
WHERE captured_at = (SELECT MAX(captured_at) FROM pool_snapshots)
ORDER BY tvl_usd DESC
LIMIT 10;
```

**24h Volume over time** — second line chart for activity dynamics.

**Trades and Users** — two big number widgets showing the latest values.

### 4.3 Assemble the Dashboard

New → Dashboard → drag widgets in, arrange them on the grid. Enable auto-refresh every 60 minutes — the dashboard will update itself.

---

## Phase 5 — Optional Extensions

Once the base stack is running, consider adding:

- **Metabase alerts** — notification if TVL drops more than 10% in an hour
- **dbt** — move transformations out of Python and into SQL queries running directly in Postgres (this is the modern ELT approach)
- **More endpoints** — add `/v1/stats/operations` to analyze operation types (swaps vs liquidity provision)
- **Idempotency** — make the load task safe to re-run (`INSERT ON CONFLICT DO NOTHING`)
