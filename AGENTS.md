# OpenCode Agent Instructions (stonfi_monitor)

- If Airflow tasks need XCom values, prefer `ti.xcom_pull(task_ids="<upstream_task>", key="<xcom_key>")` explicitly for Airflow 3.2.0. (Otherwise agents may assume default upstream selection works.)
- Use `docker compose exec -T postgres psql -U airflow -d airflow -c "..."` to verify DB state after DAG runs. (Agents commonly forget to verify writes directly in Postgres.)
- Only trust executable sources (DAG code, `init.sql`, docker-compose) over `ston_monitor_plan.md` when behavior differs. (Agents might otherwise follow stale/incorrect API examples.)
- When debugging `Empty XCom` / `Empty data` in the pipeline, check Airflow XCom existence in UI for the upstream task before touching transformation logic. (Agents may chase API/data issues first.)
- Keep all DAG code in `dags/` and ensure it’s mounted by docker-compose to `/opt/airflow/dags`. (Agents may edit files in the wrong folder and see no effect.)

- For Phase 3 verification, confirm Postgres writes directly with:
  - `docker compose exec -T postgres psql -U airflow -d airflow -c "SELECT MAX(captured_at) FROM dex_stats;"`
  - `docker compose exec -T postgres psql -U airflow -d airflow -c "SELECT COUNT(*) FROM pool_snapshots;"`
- For Phase 4 (Metabase), verify database connection uses Docker hostname `postgres` (not `localhost`).
