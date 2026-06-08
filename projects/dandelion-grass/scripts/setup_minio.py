"""
Crée le bucket MinIO 'plants' et configure les dossiers de base.
À lancer UNE SEULE FOIS après le premier docker compose up.

Usage :
    docker compose exec api python /workspace/scripts/setup_minio.py
"""
import os
import boto3
from botocore.exceptions import ClientError

S3_ENDPOINT_URL    = os.getenv("S3_ENDPOINT_URL",    "http://minio:9000")
AWS_ACCESS_KEY_ID  = os.getenv("AWS_ACCESS_KEY_ID",  "minio")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "minio12345")
S3_BUCKET          = os.getenv("S3_BUCKET",          "plants")

s3 = boto3.client(
    "s3",
    endpoint_url=S3_ENDPOINT_URL,
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
)

try:
    s3.create_bucket(Bucket=S3_BUCKET)
    print(f"✓ Bucket '{S3_BUCKET}' créé")
except ClientError as e:
    if e.response["Error"]["Code"] in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
        print(f"✓ Bucket '{S3_BUCKET}' existe déjà")
    else:
        raise

# Créer les préfixes (dossiers virtuels)
for prefix in ["plants/dandelion/.keep", "plants/grass/.keep",
               "models/.keep", "mlflow/.keep", "monitoring/.keep"]:
    s3.put_object(Bucket=S3_BUCKET, Key=prefix, Body=b"")

print("✓ Structure MinIO prête :")
print("   plants/dandelion/   plants/grass/   models/   mlflow/   monitoring/")
