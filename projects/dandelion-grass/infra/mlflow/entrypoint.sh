#!/bin/bash
set -e

# MLflow avec allowed-hosts pour autoriser les connexions depuis les conteneurs Docker
exec mlflow server \
  --backend-store-uri "${BACKEND_STORE_URI:-sqlite:///mlflow.db}" \
  --default-artifact-root "${MLFLOW_ARTIFACT_ROOT:-s3://plants/mlflow}" \
  --host 0.0.0.0 \
  --port 5000 \
  --serve-artifacts \
  --allowed-hosts "*"
