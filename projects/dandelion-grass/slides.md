---
marp: true
theme: default
paginate: true
style: |
  section {
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 22px;
  }
  h1 { color: #2E7D32; font-size: 40px; }
  h2 { color: #1565C0; font-size: 30px; border-bottom: 2px solid #1565C0; padding-bottom: 6px; }
  code { background: #f4f4f4; padding: 2px 6px; border-radius: 4px; }
  table { font-size: 18px; }
  .small { font-size: 16px; }
---

# Détection Pissenlit vs Herbe
## Pipeline MLOps de bout en bout

**Bloc 4 — Solutions d'Intelligence Artificielle**

Cyprien Cazenave — 2026

---

## Slide 1 — Contexte métier

**Problème :** Identifier automatiquement si une image de pelouse contient du **pissenlit** (*Taraxacum officinale*) ou de l'**herbe**.

**Cas d'usage concrets :**
- Jardinerie & paysagisme : audit automatisé des espaces verts
- Agriculture de précision : cartographie des mauvaises herbes
- Applications grand public : diagnostic jardin par photo

**Enjeu MLOps :**
> Une solution IA de production ne se réduit pas au modèle.
> Il faut industrialiser l'entraînement, le déploiement, la surveillance et le réentraînement.

---

## Slide 2 — Cahier des charges

| Critère | Exigence |
|---|---|
| **Tâche** | Classification binaire (pissenlit / herbe) |
| **Précision cible** | ≥ 85% accuracy sur validation |
| **Latence API** | < 200 ms par prédiction |
| **Disponibilité** | Rechargement du modèle sans redémarrage |
| **Monitoring** | Détection de drift quotidienne |
| **Réentraînement** | Automatique si drift ≥ 30 % des features |
| **CI/CD** | Tests + build Docker sur chaque commit |
| **Infrastructure** | Containerisée, reproductible |

---

## Slide 3 — Données

**Source :** URLs d'images publiques (fichiers `data/raw_urls/dandelion.txt` et `grass.txt`)

**Pipeline d'ingestion :**
```
URLs texte → Airflow DAG → téléchargement JPEG → MinIO (S3)
                                                      ↓
                                              Postgres (registre)
```

**Distribution :**
- ~50 % pissenlit / ~50 % herbe (dataset équilibré)
- Images RGB 224×224 après resize
- Features extraites pour monitoring : `mean_r`, `mean_g`, `mean_b`, `brightness`, `confidence`

---

## Slide 4 — Modèle ML

**Architecture :** ResNet18 (PyTorch) avec fine-tuning progressif

```
ImageNet weights → [Geler couches conv] → Fine-tune FC → [Dégeler tout] → Fine-tune global
```

**Optimisations clés :**
- Data augmentation : rotation, color jitter, random erasing
- Early stopping (patience = 7)
- AdamW optimizer, lr = 5e-4

**Résultats :**

| | Baseline (3 epochs) | Optimisé (25 epochs) |
|---|---|---|
| Val Accuracy | 45 % | **92 %** |
| Val Loss | 6.49 | **0.35** |
| Temps | ~1 min | ~3 min |

---

## Slide 5 — Architecture technique globale

```
┌──────────────────────────────────────────────────────┐
│                   Docker Compose                     │
│                                                      │
│  [Postgres]──[MinIO]──[MLflow]──[Airflow]           │
│      ↑           ↑       ↑          ↑               │
│  données     images   tracking  pipelines            │
│                                                      │
│  [FastAPI /predict] ←─── modèle TorchScript         │
│       ↓ métriques                                    │
│  [Prometheus] ──→ [Grafana dashboard]                │
│                                                      │
│  [Streamlit webapp]  [Evidently reports]             │
└──────────────────────────────────────────────────────┘
```

**9 services** orchestrés par Docker Compose — stack reproductible en 1 commande.

---

## Slide 6 — Pipeline de données et d'entraînement

```
data/raw_urls/      Airflow              MinIO
dandelion.txt  →  ingest_images  →  plants/images/
grass.txt                               ↓
                                   S3ImageDataset (PyTorch)
                                        ↓
                              train_register DAG
                                        ↓
                               MLflow experiment
                                        ↓
                            TorchScript → MinIO plants/models/
                                        ↓
                           POST /admin/reload → API hot-reload
```

---

## Slide 7 — Stack technique

| Couche | Technologie |
|---|---|
| **ML** | PyTorch 2.3, ResNet18, torchvision |
| **Tracking** | MLflow 2.15 |
| **Orchestration** | Apache Airflow 2.9 |
| **Stockage** | PostgreSQL 16 + MinIO (S3-compatible) |
| **API** | FastAPI 0.115 + Uvicorn |
| **Monitoring** | Evidently 0.4, Prometheus, Grafana |
| **Frontend** | Streamlit 1.38 |
| **CI/CD** | GitHub Actions + Docker Buildx |
| **Conteneurisation** | Docker Compose + Kubernetes (manifests) |
| **Tests** | pytest (26 tests) |

---

## Slide 8 — Pipeline CI/CD — Vue d'ensemble

**Déclenchement :** sur chaque `push` ou `pull_request` vers `main`

```
┌─────────────────────────────────────────────────────┐
│              GitHub Actions Workflow                │
│                                                     │
│  [Push code] ──→ [Lint & Test] ──→ [Build & Push]  │
│                       ↓                   ↓        │
│                  ruff check        ghcr.io image   │
│                  pytest (26)     sha-XXXXXXX:latest │
└─────────────────────────────────────────────────────┘
```

**Fichier :** `.github/workflows/ci.yml`

**Principe :** si les tests échouent → le build ne se lance pas.
L'image Docker ne change que si le code est correct.

---

## Slide 9 — Pipeline CI/CD — Détail des jobs

**Job 1 — Lint & Test**
```yaml
- ruff check api/ tests/ --ignore E501
- pytest tests/ -v --tb=short   # 26 tests
```
Tests sans dépendances réseau (mocks Postgres, MinIO, modèle).

**Job 2 — Build & Push** *(push sur main uniquement)*
```yaml
- docker buildx build ./api
- push → ghcr.io/cazenavealbertschool/mlops-dandelion-api:sha-abc1234
- push → ghcr.io/.../mlops-dandelion-api:latest
```

**Optimisations :**
- Cache pip entre les runs → tests ~2× plus rapides
- Cache Docker layer (GHA cache) → builds ~3× plus rapides

---

## Slide 10 — CI/CD — Résultats

**26 tests automatisés :**

| Catégorie | Tests | Couvre |
|---|---|---|
| API smoke | 1 | `/healthz` |
| Prédictions | 14 | `/predict`, `/metrics`, `/admin/drift-score` |
| Monitoring | 11 | Evidently, `run_drift_check`, extraction features |

**Réentraînement planifié :**

Fichier `.github/workflows/retrain.yml` :
- Déclenché **chaque lundi 03:00 UTC** (schedule cron)
- Déclenché **manuellement** depuis l'UI GitHub
- Crée une **issue GitHub automatique** si le trigger échoue

---

## Slide 11 — Monitoring — Architecture

```
                  FastAPI /predict
                       ↓
              Log prédictions → Postgres
              (label, confidence, mean_r/g/b, brightness)
                       ↓
           [Airflow monitoring_drift_check — quotidien]
                       ↓
              Evidently DatasetDriftMetric
              ┌──────────────────────────┐
              │  Référence : 500 oldest  │
              │  Courant   : 7 derniers j│
              └──────────────────────────┘
                       ↓
              drift_score → API Prometheus gauge
                       ↓
               Grafana dashboard (temps réel)
```

---

## Slide 12 — Monitoring — Détection de drift Evidently

**Features surveillées :**
- `confidence` — le modèle est-il plus incertain ?
- `mean_r`, `mean_g`, `mean_b` — les images ont-elles changé de couleur ?
- `brightness` — changement de conditions d'éclairage ?

**Seuil de déclenchement :** `drift_score ≥ 0.3` (30 % des colonnes driftent)

**Outputs automatiques :**
- Rapport HTML → MinIO `plants/monitoring/drift_report_latest.html`
- Résumé JSON → MinIO `plants/monitoring/drift_summary_latest.json`
- Gauge Prometheus `model_drift_score` → Grafana

---

## Slide 13 — Monitoring — Grafana

**Dashboard MLOps — métriques temps réel :**

```
┌─────────────────────┬──────────────────────┐
│  Requêtes totales   │  Latence p50 / p95   │
│  api_requests_total │  api_latency_seconds │
├─────────────────────┼──────────────────────┤
│  Distribution labels│  Drift score (gauge) │
│  grass / dandelion  │  model_drift_score   │
└─────────────────────┴──────────────────────┘
```

**Scraping Prometheus** toutes les 10 secondes depuis `api:8000/metrics`

---

## Slide 14 — Réentraînement automatique — Schéma global

```
[monitoring_drift_check]         [ct_retrain_deploy]
        ↓                                ↓
  run_evidently                   check_condition
        ↓                          (>= 10 images ?)
  alert_on_drift                         ↓
        ↓                          ┌─────┴──────┐
  decide_retrain                train_model    skip
  (drift ≥ 30 % ?)                   ↓
        ↓                        reload_api
  trigger_retrain ──────→   (hot-reload sans restart)
  (TriggerDagRunOperator)
```

**Double garde-fou :**
1. Monitoring déclenche seulement si drift réel
2. Retrain s'exécute seulement si données suffisantes (≥ 10 images)

---

## Slide 15 — DAG monitoring_drift_check

**Schedule :** quotidien à 06:00 UTC

```
check_data_availability  →  run_evidently  →  alert_on_drift
                                                     ↓
                                            decide_retrain (@task.branch)
                                           /                    \
                                  trigger_retrain        no_retrain_needed
                              (TriggerDagRunOperator)      (EmptyOperator)
```

- `check_data_availability` : vérifie que ≥ 30 prédictions existent (7 derniers jours)
- `run_evidently` : exécute `monitoring.drift_check.run_drift_check()`
- `decide_retrain` : branche selon `drift_score >= DRIFT_THRESHOLD`

---

## Slide 16 — DAG ct_retrain_deploy

**Schedule :** lundi 03:00 UTC + déclenchement par monitoring si drift

```
check_condition
(COUNT images >= 10 ?)
        ↓
   branch_task
  /           \
train_model   skip
    ↓
reload_api
(POST /admin/reload)
```

**train_model :**
- Appelle `src.train_optimized.train_one_run_optimized(epochs=10)`
- Log métriques dans MLflow
- Upload modèle TorchScript → MinIO

**reload_api :**
- POST `/admin/reload?model_s3_uri=s3://plants/models/...`
- L'API charge le nouveau modèle sans redémarrage du container

---

## Slide 17 — Résultats & Bilan

**Performance du modèle :**

| Métrique | Valeur |
|---|---|
| Accuracy validation | **92 %** |
| Baseline (3 epochs) | 45 % |
| Gain | **+104 %** |
| Latence inférence | < 100 ms |
| Val Loss | 0.35 (vs 6.49 baseline) |

**Maturité MLOps atteinte :**

✅ Pipeline de données automatisé (Airflow)
✅ Tracking des expériences (MLflow)
✅ API de serving avec métriques (FastAPI + Prometheus)
✅ CI/CD (GitHub Actions, 26 tests, build Docker)
✅ Monitoring de drift (Evidently + Grafana)
✅ Réentraînement automatique déclenché par drift

---

## Questions ?

**Repo GitHub :** `github.com/CazenaveAlbertSchool/Bloc4`

**Pour reproduire :**
```bash
git clone git@github.com:CazenaveAlbertSchool/Bloc4.git
cd Bloc4/projects/dandelion-grass
docker compose --env-file compose.env up -d --build
```

**Contact :** cyprien.cazenave@gmail.com
