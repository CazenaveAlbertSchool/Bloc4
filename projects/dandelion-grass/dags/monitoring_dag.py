from datetime import datetime
import os
from airflow import DAG
from airflow.decorators import task

with DAG(
    dag_id="monitoring_drift_check",
    start_date=datetime(2024, 1, 1),
    schedule_interval="0 6 * * *",  # daily at 06:00 UTC
    catchup=False,
    tags=["monitoring", "evidently", "drift"],
    doc_md="""
## Daily Drift Check

Runs Evidently against the `predictions` table in Postgres.

- **reference**: oldest 500 logged predictions
- **current**: last 7 days of predictions
- Uploads HTML report + JSON summary to MinIO (`plants/monitoring/`)
- Pushes `drift_score` to the API Prometheus gauge via `POST /admin/drift-score`
- Raises a warning task if drift is detected
""",
) as dag:

    @task
    def check_data_availability() -> int:
        import psycopg2
        db_url = os.getenv("DATABASE_URL", "postgresql://plants:plants@postgres:5432/plants")
        with psycopg2.connect(db_url) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM predictions WHERE ts >= NOW() - INTERVAL '7 days'"
            )
            return cur.fetchone()[0]

    @task
    def run_evidently(n_recent: int) -> dict:
        if n_recent < 30:
            print(f"Only {n_recent} recent predictions — skipping drift check (need 30+).")
            return {"status": "skipped", "n_current": n_recent}
        import sys
        sys.path.insert(0, "/opt/airflow")
        from monitoring.drift_check import run_drift_check
        return run_drift_check(days_back=7)

    @task
    def alert_on_drift(summary: dict):
        """Log a visible warning if drift was detected."""
        if summary.get("status") == "skipped":
            print("Drift check was skipped due to insufficient data.")
            return
        drift_score = summary.get("drift_score", 0.0)
        drift_detected = summary.get("drift_detected", False)
        if drift_detected:
            print(
                f"⚠️  DATA DRIFT DETECTED — score={drift_score:.3f}  "
                f"(ref={summary.get('n_reference')}, cur={summary.get('n_current')})\n"
                f"Column details: {summary.get('columns', {})}\n"
                "Action required: review data pipeline or trigger retraining."
            )
        else:
            print(
                f"✅  No drift detected — score={drift_score:.3f}  "
                f"(ref={summary.get('n_reference')}, cur={summary.get('n_current')})"
            )

    n = check_data_availability()
    summary = run_evidently(n)
    alert_on_drift(summary)
