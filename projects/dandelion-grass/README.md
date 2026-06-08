# ML-Ops Repository 🚀

Collection de projets MLOps opérationnels et templates réutilisables.

## 📁 Projects

### 🌿 [Dandelion vs Grass](./MLOPS/MLOps%20Dandelion%20Grass%20Overview/)
**Status**: ✅ **FULLY OPERATIONAL**
- Pipeline MLOps complet (Ingest → Train → Serve → Monitor)
- ResNet18 avec 90% accuracy
- Docker Compose multi-services
- FastAPI + Streamlit + MLflow + Airflow

---

# MLOps — Dandelion vs Grass (Starter Repo)

This is a **ready-to-extend** scaffold implementing the project structure, dev Docker stack, API & WebApp skeletons, sample Airflow DAGs, CI template, and K8s manifests.

> Focus: **operational pipeline** (ingest → train/log → serve → monitor → retrain). The model is a placeholder; swap with your preferred framework (PyTorch/FastAI/TF).

## Quick Start (Dev with Docker Compose)

1) Create a `.env` file for Docker Compose (optional; defaults are provided via `compose.env`).  
2) Start services:
```bash
docker compose --env-file compose.env up -d --build
```
3) Open UIs:
- **API**: http://localhost:8000/docs  
- **WebApp (Streamlit)**: http://localhost:8501  
- **MinIO**: http://localhost:9001  (user: `minio`, pass: `minio12345`)  
- **MLflow**: http://localhost:5000  
- **Airflow**: http://localhost:8080  (user: `airflow`, pass: `airflow`)

4) Seed URLs (edit the two text files in `data/raw_urls/` first):
```bash
docker compose exec api python scripts/seed_urls_to_db.py
```

5) Trigger **ingestion** DAG in Airflow UI (after the webserver is healthy). Uploaded images will appear in MinIO under `plants/` prefix.

6) After you implement training, run it locally or via the `train_register_dag.py` DAG, then set `MODEL_S3_URI` or `MODEL_PATH` for the API.

## Services in Docker Compose
- **Postgres** (data registry):	`plants` DB with table `plants_data(url_source, url_s3, label)`
- **MinIO** (S3): object store for raw images and models
- **MLflow**: experiment tracker & model registry (backed by MinIO for artifacts)
- **Airflow**: ingests data, (later) triggers training & deploy
- **API**: FastAPI `/predict` endpoint, Prometheus metrics at `/metrics`
- **WebApp**: Streamlit client for quick manual testing

## Project Structure
```
mlops-dandelion-grass/
├─ apps/
│  ├─ api/                 # FastAPI
│  └─ webapp/              # Streamlit UI
├─ data/
│  ├─ raw_urls/            # URL lists for seeding (edit these)
│  └─ samples/             # tiny sample images (optional)
├─ dags/                   # Airflow DAGs
├─ infra/
│  ├─ airflow/             # Airflow Docker build & configs
│  ├─ mlflow/              # MLflow Docker
│  ├─ k8s/                 # K8s manifests
│  └─ grafana/             # (optional) dashboards
├─ ml/                     # Model code (placeholders)
├─ scripts/                # Utility scripts (seed URLs, etc.)
├─ tests/                  # Basic tests
├─ .github/workflows/      # CI/CD template
├─ docker-compose.yml
└─ compose.env
```

## Notes
- Replace placeholders in DAGs & ML code.  
- For K8s, update image names and `MODEL_S3_URI` / secrets in manifests.  
- Grafana/Prometheus not included by default to keep the stack light; add later.

Good luck & have fun!

## Training & Reload (Full)
- In Airflow, trigger `train_register` to train a ResNet18 with MLflow logging. The trained TorchScript model is uploaded to MinIO (under `models/`), and the API is hot‑reloaded to use the new S3 model.
- Or, run inside the `api` container:
```bash
python -m ml.train  # prints MODEL_URI
curl -X POST "http://localhost:8000/admin/reload?model_s3_uri=s3://plants/models/..." 
```