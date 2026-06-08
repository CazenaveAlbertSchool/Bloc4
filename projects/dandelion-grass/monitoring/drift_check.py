"""
Evidently drift detection for the Dandelion vs Grass classifier.

Compares the distribution of recent predictions (last 7 days) against a
reference window (the first stable batch of predictions). Tracks:
  - image feature drift  (mean R, G, B, brightness)
  - confidence score drift
  - prediction label shift

Outputs:
  - HTML report  →  MinIO: plants/monitoring/drift_report_latest.html
  - JSON summary →  MinIO: plants/monitoring/drift_summary_latest.json
  - return dict  →  consumed by the Airflow DAG to push score to the API
"""

import io
import json
import os
import tempfile

import boto3
import pandas as pd
import psycopg2
import requests
from evidently.metric_preset import DataDriftPreset
from evidently.metrics import ColumnDriftMetric, DatasetDriftMetric
from evidently.report import Report

# ── Config ────────────────────────────────────────────────────────
DB_URL = os.getenv("DATABASE_URL", "postgresql://plants:plants@postgres:5432/plants")
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "http://minio:9000")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "minio")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "minio12345")
S3_BUCKET = os.getenv("S3_BUCKET", "plants")
API_URL = os.getenv("API_URL", "http://api:8000")

FEATURE_COLS = ["confidence", "mean_r", "mean_g", "mean_b", "brightness"]
MIN_ROWS = 30  # minimum predictions needed to run a meaningful check


def _s3_client():
    return boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT_URL,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    )


def _load_df(query: str) -> pd.DataFrame:
    with psycopg2.connect(DB_URL) as conn:
        return pd.read_sql(query, conn)


def _get_reference_df() -> pd.DataFrame:
    """Oldest 500 predictions as the reference distribution."""
    return _load_df("""
        SELECT ts, label, confidence, mean_r, mean_g, mean_b, brightness
        FROM predictions
        ORDER BY ts ASC
        LIMIT 500
    """)


def _get_current_df(days_back: int = 7) -> pd.DataFrame:
    return _load_df(f"""
        SELECT ts, label, confidence, mean_r, mean_g, mean_b, brightness
        FROM predictions
        WHERE ts >= NOW() - INTERVAL '{days_back} days'
        ORDER BY ts DESC
        LIMIT 500
    """)


def _upload_to_s3(local_path: str, s3_key: str, content_type: str = "application/octet-stream"):
    _s3_client().upload_file(
        local_path, S3_BUCKET, s3_key,
        ExtraArgs={"ContentType": content_type},
    )


def _push_drift_score_to_api(drift_score: float, drift_detected: bool):
    try:
        r = requests.post(
            f"{API_URL}/admin/drift-score",
            params={"score": drift_score, "drift_detected": str(drift_detected).lower()},
            timeout=10,
        )
        r.raise_for_status()
    except Exception as exc:
        print(f"[drift_check] Could not push score to API: {exc}")


def run_drift_check(days_back: int = 7) -> dict:
    """Run full Evidently check. Returns a summary dict."""
    current_df = _get_current_df(days_back=days_back)
    reference_df = _get_reference_df()

    if len(current_df) < MIN_ROWS:
        print(f"[drift_check] Not enough current data ({len(current_df)} rows, need {MIN_ROWS}). Skipping.")
        return {"status": "insufficient_data", "drift_score": 0.0, "n_current": len(current_df)}

    if len(reference_df) < MIN_ROWS:
        print(f"[drift_check] Not enough reference data ({len(reference_df)} rows). Skipping.")
        return {"status": "insufficient_data", "drift_score": 0.0, "n_reference": len(reference_df)}

    # Avoid overlap: reference = everything older than current window
    cutoff = current_df["ts"].min()
    reference_df = reference_df[reference_df["ts"] < cutoff]
    if len(reference_df) < MIN_ROWS:
        # Fallback: use first half / second half split
        all_df = pd.concat([reference_df, current_df]).sort_values("ts")
        mid = len(all_df) // 2
        reference_df = all_df.iloc[:mid][FEATURE_COLS].reset_index(drop=True)
        current_df = all_df.iloc[mid:][FEATURE_COLS].reset_index(drop=True)
    else:
        reference_df = reference_df[FEATURE_COLS].reset_index(drop=True)
        current_df = current_df[FEATURE_COLS].reset_index(drop=True)

    # ── Build Evidently report ─────────────────────────────────────
    report = Report(metrics=[
        DatasetDriftMetric(),
        ColumnDriftMetric(column_name="confidence"),
        ColumnDriftMetric(column_name="mean_r"),
        ColumnDriftMetric(column_name="mean_g"),
        ColumnDriftMetric(column_name="mean_b"),
        ColumnDriftMetric(column_name="brightness"),
    ])
    report.run(reference_data=reference_df, current_data=current_df)

    result = report.as_dict()
    metrics = result["metrics"]

    dataset_result = metrics[0]["result"]
    drift_score = float(dataset_result.get("share_of_drifted_columns", 0.0))
    drift_detected = bool(dataset_result.get("dataset_drift", False))

    # ── Upload HTML report to MinIO ────────────────────────────────
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
        html_path = f.name
    report.save_html(html_path)
    _upload_to_s3(html_path, "monitoring/drift_report_latest.html", "text/html")

    # ── Build summary ──────────────────────────────────────────────
    column_results = {}
    for m in metrics[1:]:
        col = m["metric"].split("(")[-1].rstrip(")")
        column_results[col] = {
            "drift_detected": m["result"].get("drift_detected"),
            "p_value": m["result"].get("p_value"),
            "stattest": m["result"].get("stattest_name"),
        }

    summary = {
        "status": "ok",
        "drift_detected": drift_detected,
        "drift_score": drift_score,
        "n_reference": len(reference_df),
        "n_current": len(current_df),
        "columns": column_results,
    }

    # ── Upload JSON summary to MinIO ───────────────────────────────
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        json.dump(summary, f, indent=2)
        json_path = f.name
    _upload_to_s3(json_path, "monitoring/drift_summary_latest.json", "application/json")

    # ── Push score to API Prometheus gauge ─────────────────────────
    _push_drift_score_to_api(drift_score, drift_detected)

    print(f"[drift_check] drift_detected={drift_detected} score={drift_score:.3f} "
          f"(ref={len(reference_df)}, cur={len(current_df)})")
    return summary


if __name__ == "__main__":
    result = run_drift_check()
    print(json.dumps(result, indent=2))
