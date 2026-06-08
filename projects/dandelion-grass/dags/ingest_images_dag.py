from datetime import datetime
import os, io, uuid, requests
from PIL import Image
import psycopg2, boto3
from airflow import DAG
from airflow.decorators import task

DB_URL = os.getenv("DATABASE_URL", "postgresql://plants:plants@postgres:5432/plants")
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "http://minio:9000")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "minio")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "minio12345")
S3_BUCKET = os.getenv("S3_BUCKET", "plants")

def get_conn():
    return psycopg2.connect(DB_URL)

def s3_client():
    return boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT_URL,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    )

with DAG(
    dag_id="ingest_images",
    start_date=datetime(2024, 1, 1),
    schedule_interval=None,
    catchup=False,
    tags=["ingest","minio"],
) as dag:

    @task
    def fetch_pending(limit: int = 50):
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT url_source, label FROM plants_data WHERE url_s3 IS NULL LIMIT %s", (limit,))
            rows = cur.fetchall()
        return [{"url_source": r[0], "label": r[1]} for r in rows]

    @task
    def process_items(rows: list[dict]):
        s3 = s3_client()
        ok, fail = 0, 0
        for row in rows:
            try:
                resp = requests.get(row["url_source"], timeout=20)
                resp.raise_for_status()
                img = Image.open(io.BytesIO(resp.content)).convert("RGB")
                img_buf = io.BytesIO()
                img.save(img_buf, format="JPEG", quality=90)
                img_buf.seek(0)
                key = f"plants/{row['label']}/{uuid.uuid4().hex}.jpg"
                s3.put_object(Bucket=S3_BUCKET, Key=key, Body=img_buf.getvalue(), ContentType="image/jpeg")
                with get_conn() as conn, conn.cursor() as cur:
                    cur.execute("UPDATE plants_data SET url_s3=%s WHERE url_source=%s", (f"s3://{S3_BUCKET}/{key}", row["url_source"]))
                ok += 1
            except Exception as e:
                print("FAILED", row["url_source"], e)
                fail += 1
        print(f"done ok={ok} fail={fail}")
        return {"ok": ok, "fail": fail}

    rows = fetch_pending()
    _ = process_items(rows)
