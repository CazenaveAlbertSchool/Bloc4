from datetime import datetime
import os
from airflow import DAG
from airflow.decorators import task
from airflow.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.operators.empty import EmptyOperator

# Trigger retrain when at least this share of feature columns drifts
DRIFT_THRESHOLD = float(os.getenv("DRIFT_THRESHOLD", "0.3"))

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
- Triggers `ct_retrain_deploy` DAG automatically if `drift_score >= DRIFT_THRESHOLD`
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
    def alert_on_drift(summary: dict) -> dict:
        """Log result and return summary unchanged for the downstream branch."""
        if summary.get("status") == "skipped":
            print("Drift check was skipped due to insufficient data.")
            return summary
        drift_score = summary.get("drift_score", 0.0)
        drift_detected = summary.get("drift_detected", False)
        if drift_detected:
            print(
                f"⚠️  DATA DRIFT DETECTED — score={drift_score:.3f}  "
                f"(ref={summary.get('n_reference')}, cur={summary.get('n_current')})\n"
                f"Column details: {summary.get('columns', {})}\n"
                f"Threshold={DRIFT_THRESHOLD} — will trigger retrain if score >= threshold."
            )
        else:
            print(
                f"✅  No drift detected — score={drift_score:.3f}  "
                f"(ref={summary.get('n_reference')}, cur={summary.get('n_current')})"
            )
        return summary

    @task.branch
    def decide_retrain(summary: dict) -> str:
        """Trigger retraining if drift_score crosses the threshold."""
        status = summary.get("status", "")
        drift_score = summary.get("drift_score", 0.0)
        drift_detected = summary.get("drift_detected", False)

        if status == "ok" and drift_detected and drift_score >= DRIFT_THRESHOLD:
            print(
                f"Drift score {drift_score:.3f} >= threshold {DRIFT_THRESHOLD} "
                "→ triggering ct_retrain_deploy."
            )
            return "trigger_retrain"

        print(
            f"No retrain needed (status={status}, score={drift_score:.3f}, "
            f"threshold={DRIFT_THRESHOLD})."
        )
        return "no_retrain_needed"

    # ── Trigger retraining DAG ────────────────────────────────────
    trigger_retrain = TriggerDagRunOperator(
        task_id="trigger_retrain",
        trigger_dag_id="ct_retrain_deploy",
        conf={"reason": "drift_detected_by_monitoring"},
        wait_for_completion=False,
        reset_dag_run=True,
    )

    no_retrain_needed = EmptyOperator(task_id="no_retrain_needed")

    # ── Wire the DAG ──────────────────────────────────────────────
    n = check_data_availability()
    summary = run_evidently(n)
    alerted = alert_on_drift(summary)
    decision = decide_retrain(alerted)
    decision >> [trigger_retrain, no_retrain_needed]
