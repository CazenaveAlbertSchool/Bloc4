# Dandelion vs Grass — MLOps Pipeline

Classification d'images (pissenlit / herbe) industrialisée de bout en bout :
ingestion → entraînement → serving → monitoring → réentraînement automatique.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Docker Compose                           │
│                                                                 │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌────────────┐  │
│  │ Postgres │   │  MinIO   │   │  MLflow  │   │  Airflow   │  │
│  │ (données)│   │(images & │   │(tracking)│   │(pipelines) │  │
│  └──────────┘   │ modèles) │   └──────────┘   └────────────┘  │
│                 └──────────┘                                    │
│  ┌──────────┐   ┌──────────┐   ┌────────────┐  ┌──────────┐  │
│  │  FastAPI │   │Streamlit │   │ Prometheus │  │ Grafana  │  │
│  │  /predict│   │  (UI)    │   │ (métriques)│  │(dashbrd) │  │
│  └──────────┘   └──────────┘   └────────────┘  └──────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Structure du projet

```
dandelion-grass/
├── api/            # FastAPI — /predict, /healthz, /metrics, hot-reload
├── src/            # Entraînement ResNet18 (PyTorch + MLflow)
├── monitoring/     # Détection de drift Evidently
├── dags/           # Pipelines Airflow (ingestion, training, monitoring, retrain)
├── retrain/        # Script standalone de réentraînement
├── k8s/            # Manifests Kubernetes (namespace + deployment)
├── notebooks/      # EDA, courbes d'entraînement, matrice de confusion
├── tests/          # 26 tests unitaires et d'intégration
├── models/         # Artefacts modèles (générés par le training)
├── infra/          # Config Airflow, MLflow, Grafana, Prometheus
├── webapp/         # Interface Streamlit
├── data/raw_urls/  # URLs sources (dandelion.txt, grass.txt)
├── Dockerfile      # Image Docker de l'API
└── docker-compose.yml
```

## Démarrage rapide

```bash
# 1. Démarrer tous les services
docker compose --env-file compose.env up -d --build

# 2. Charger les URLs en base
docker compose --env-file compose.env exec api python scripts/seed_urls_to_db.py

# 3. Dans Airflow → déclencher le DAG "ingest_images"
```

**URLs des interfaces :**

| Service | URL | Credentials |
|---|---|---|
| API (Swagger) | http://localhost:8000/docs | — |
| Streamlit | http://localhost:8501 | — |
| Airflow | http://localhost:8080 | airflow / airflow |
| MLflow | http://localhost:5001 | — |
| MinIO | http://localhost:9001 | minio / minio12345 |
| Prometheus | http://localhost:9090 | — |
| Grafana | http://localhost:3000 | admin / admin |

## Pipelines Airflow

| DAG | Déclenchement | Rôle |
|---|---|---|
| `ingest_images` | Manuel | Télécharge les images vers MinIO |
| `train_register` | Manuel | Entraîne ResNet18 + enregistre dans MLflow |
| `monitoring_drift_check` | Quotidien 06:00 UTC | Détection de drift Evidently |
| `ct_retrain_deploy` | Lundi 03:00 UTC ou si drift ≥ 30% | Réentraîne et recharge l'API |

## Modèle

- **Architecture** : ResNet18 avec fine-tuning progressif
- **Accuracy** : 92% (val), contre 45% pour le baseline
- **Framework** : PyTorch 2.3 + MLflow tracking
- **Serving** : TorchScript exporté, hot-reload sans redémarrage

## CI/CD

Pipeline GitHub Actions sur chaque push :

```
Lint (ruff) → Tests (pytest, 26 tests) → Build & Push Docker image (ghcr.io)
```

Voir `.github/workflows/ci.yml`.

## Réentraînement automatique

Le DAG `monitoring_drift_check` déclenche automatiquement `ct_retrain_deploy`
si le drift score Evidently dépasse le seuil `DRIFT_THRESHOLD` (défaut : 0.3).

```bash
# Lancer manuellement le réentraînement
docker compose --env-file compose.env exec airflow \
  python -m retrain.retrain --epochs 10
```

## Tests

```bash
docker compose --env-file compose.env exec api \
  pytest tests/ -v --tb=short
```
