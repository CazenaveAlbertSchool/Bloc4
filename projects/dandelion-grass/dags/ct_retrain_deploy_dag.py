from datetime import datetime
import os
import requests
import psycopg2
from airflow import DAG
from airflow.decorators import task, branch_task

DB_URL = os.getenv("DATABASE_URL", "postgresql://plants:plants@postgres:5432/plants")
API_URL = os.getenv("API_URL", "http://api:8000")
MIN_NEW_IMAGES = 10  # retrain only if at least this many images are available


def _count_images() -> int:
    with psycopg2.connect(DB_URL) as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM plants_data WHERE url_s3 IS NOT NULL")
        return cur.fetchone()[0]


with DAG(
    dag_id="ct_retrain_deploy",
    start_date=datetime(2024, 1, 1),
    schedule_interval="0 3 * * 1",  # every Monday at 03:00 UTC
    catchup=False,
    tags=["ct", "retrain"],
) as dag:

    @task
    def check_condition() -> bool:
        return _count_images() >= MIN_NEW_IMAGES

    @branch_task
    def branch(should: bool) -> str:
        return "train_model" if should else "skip"

    @task
    def train_model() -> str:
        from ml.train_optimized import train_one_run_optimized
        # Fewer epochs for scheduled retraining to keep runtime reasonable
        return train_one_run_optimized(epochs=10, lr=5e-4, batch_size=8, patience=4)

    @task
    def reload_api(model_uri: str) -> dict:
        try:
            r = requests.post(
                f"{API_URL}/admin/reload",
                params={"model_s3_uri": model_uri},
                timeout=60,
            )
            r.raise_for_status()
        except Exception as e:
            print(f"Failed to reload API: {e}")
        return {"reloaded": True, "uri": model_uri}

    @task
    def skip() -> dict:
        print(f"Fewer than {MIN_NEW_IMAGES} images in DB — skipping retrain.")
        return {"skipped": True}

    # ── Wire the DAG ─────────────────────────────────────────────
    cond = check_condition()
    decision = branch(cond)

    uri = train_model()
    reloaded = reload_api(uri)
    skipped = skip()

    # Branch controls which path executes; the other is marked SKIPPED
    decision >> [uri, skipped]
