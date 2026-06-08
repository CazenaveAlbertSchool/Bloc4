from datetime import datetime
import os
import requests
from airflow import DAG
from airflow.decorators import task

API_URL = os.getenv("API_URL", "http://api:8000")

with DAG(
    dag_id="train_register",
    start_date=datetime(2024, 1, 1),
    schedule_interval=None,  # manual trigger only
    catchup=False,
    tags=["train", "mlflow"],
) as dag:

    @task
    def train_model() -> str:
        from src.train_optimized import train_one_run_optimized
        return train_one_run_optimized(epochs=25, lr=5e-4, batch_size=8, patience=7)

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

    uri = train_model()
    reload_api(uri)
