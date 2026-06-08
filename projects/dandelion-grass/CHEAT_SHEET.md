# 📝 Aide-Mémoire MLOps - Commandes Essentielles

> **Cheat Sheet pour la présentation et le dépannage**

---

## 🚀 Démarrage et Arrêt

### Lancer tous les services
```bash
cd /Users/rayanekryslak-medioub/Desktop/AlbertSchool1/ML-ops/projects/dandelion-grass

# Première fois (avec build)
docker-compose --env-file compose.env up -d --build

# Démarrages suivants (plus rapide)
docker-compose --env-file compose.env up -d
```

### Vérifier l'état des services
```bash
# Voir tous les services
docker-compose ps

# Format tableau lisible
docker-compose ps --format "table {{.Service}}\t{{.Status}}\t{{.Ports}}"
```

### Arrêter tous les services
```bash
# Arrêter (données conservées)
docker-compose down

# Arrêter ET supprimer les volumes (⚠️ perte de données)
docker-compose down -v
```

### Redémarrer un service spécifique
```bash
docker-compose restart <service>

# Exemples
docker-compose restart api
docker-compose restart mlflow
docker-compose restart airflow
```

---

## 🔍 Monitoring et Logs

### Voir les logs
```bash
# Tous les services (dernières 100 lignes)
docker-compose logs --tail=100

# Service spécifique
docker-compose logs -f <service>

# Exemples
docker-compose logs -f airflow
docker-compose logs -f api
docker-compose logs -f mlflow

# Logs en temps réel (follow)
docker-compose logs -f
```

### Voir les logs d'un container spécifique
```bash
# Liste des containers
docker ps

# Logs par container ID ou nom
docker logs <container_name>
docker logs mlopsdg-airflow-1
docker logs mlopsdg-api-1
```

### Filtrer les logs
```bash
# Chercher "error" dans les logs
docker-compose logs | grep -i error

# Chercher dans un service spécifique
docker-compose logs airflow | grep -i "epoch"
```

---

## 📊 URLs et Accès

### Interfaces Web
```bash
# API Documentation (Swagger)
open http://localhost:8000/docs

# WebApp Streamlit
open http://localhost:8501

# MLflow Tracking
open http://localhost:5001

# Airflow
open http://localhost:8080
# Username: airflow
# Password: airflow

# MinIO Console
open http://localhost:9001
# Username: minio
# Password: minio12345
```

### Health Checks
```bash
# API Health
curl http://localhost:8000/healthz | jq

# API Metrics (Prometheus)
curl http://localhost:8000/metrics
```

---

## 💾 Data et Pipeline

### Seed initial des données
```bash
# Via docker-compose exec
docker-compose exec api python /workspace/scripts/seed_urls_to_db.py

# Via docker exec direct
docker exec mlopsdg-api-1 python /workspace/scripts/seed_urls_to_db.py
```

### Vérifier la base de données
```bash
# Se connecter à PostgreSQL
docker-compose exec postgres psql -U plants -d plants

# Puis dans psql:
# Liste des tables
\dt

# Voir les données
SELECT COUNT(*) FROM plants_data;
SELECT label, COUNT(*) FROM plants_data GROUP BY label;

# Quitter
\q
```

### Vérifier MinIO S3
```bash
# Lister les buckets
docker-compose exec api python3 << 'EOF'
import boto3, os
s3 = boto3.client("s3",
    endpoint_url=os.getenv("S3_ENDPOINT_URL"),
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"))
print(s3.list_buckets())
EOF

# Lister les objets dans le bucket plants
docker-compose exec api python3 << 'EOF'
import boto3, os
s3 = boto3.client("s3",
    endpoint_url=os.getenv("S3_ENDPOINT_URL"),
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"))
response = s3.list_objects_v2(Bucket='plants', MaxKeys=10)
if 'Contents' in response:
    for obj in response['Contents']:
        print(obj['Key'])
EOF
```

---

## 🔄 Airflow DAGs

### Lister les DAGs
```bash
docker-compose exec airflow airflow dags list
```

### Déclencher un DAG
```bash
# Ingestion
docker-compose exec airflow airflow dags trigger ingest_images

# Training
docker-compose exec airflow airflow dags trigger train_register

# Continuous Training
docker-compose exec airflow airflow dags trigger ct_retrain_deploy
```

### Voir les runs d'un DAG
```bash
# Tous les runs
docker-compose exec airflow airflow dags list-runs -d ingest_images

# Seulement les 5 derniers
docker-compose exec airflow airflow dags list-runs -d train_register | head -6
```

### État d'un DAG
```bash
docker-compose exec airflow airflow dags state <dag_id> <execution_date>
```

### Activer/Désactiver un DAG
```bash
# Activer
docker-compose exec airflow airflow dags unpause <dag_id>

# Désactiver
docker-compose exec airflow airflow dags pause <dag_id>
```

---

## 🧠 Training

### Entraînement standard
```bash
docker-compose exec airflow python3 -m ml.train
```

### Entraînement optimisé
```bash
docker-compose exec airflow python3 -m ml.train_optimized
```

### Entraînement avec logs en temps réel
```bash
docker-compose exec airflow python3 -m ml.train_optimized 2>&1 | tee /tmp/training.log
```

### Monitoring du training
```bash
# Dans un terminal séparé
watch -n 2 "docker logs mlopsdg-airflow-1 2>&1 | grep 'Epoch' | tail -5"
```

---

## 🔮 Prédictions

### Via API (curl)
```bash
# Prédiction simple
curl -X POST http://localhost:8000/predict \
  -F "file=@/path/to/image.jpg" | jq

# Exemple avec image de test
curl -o /tmp/test.jpg "https://upload.wikimedia.org/wikipedia/commons/thumb/3/31/Dandelion-Taraxacum_officinale.jpg/320px-Dandelion-Taraxacum_officinale.jpg"

curl -X POST http://localhost:8000/predict \
  -F "file=@/tmp/test.jpg" | jq
```

### Recharger le modèle dans l'API
```bash
# Avec un modèle S3 spécifique
MODEL_URI="s3://plants/models/resnet18_optimized_1762505915.pt"
curl -X POST "http://localhost:8000/admin/reload?model_s3_uri=${MODEL_URI}" | jq

# Recharger depuis la variable d'environnement
curl -X POST "http://localhost:8000/admin/reload" | jq
```

### Batch predictions (via Python)
```bash
docker-compose exec api python3 << 'EOF'
import requests
import os

# Prédire plusieurs images
images = ['/tmp/test1.jpg', '/tmp/test2.jpg']
for img_path in images:
    if os.path.exists(img_path):
        with open(img_path, 'rb') as f:
            response = requests.post(
                'http://localhost:8000/predict',
                files={'file': f}
            )
            print(f"{img_path}: {response.json()}")
EOF
```

---

## 📈 MLflow

### API REST MLflow
```bash
# Lister les expériences
curl -s http://localhost:5001/api/2.0/mlflow/experiments/list | jq

# Chercher les runs
curl -s -X POST http://localhost:5001/api/2.0/mlflow/runs/search \
  -H "Content-Type: application/json" \
  -d '{}' | jq
```

### Comparer les modèles
```bash
# Via l'interface web
open http://localhost:5001

# Naviguer vers Experiments → dandelion_vs_grass → Compare runs
```

---

## 🔧 Dépannage

### Services qui ne démarrent pas

#### Port déjà utilisé
```bash
# Trouver qui utilise le port
lsof -i:5001
lsof -i:8000
lsof -i:8080

# Tuer le processus
kill -9 <PID>

# Ou modifier le port dans compose.env
```

#### Problème de mémoire
```bash
# Voir l'utilisation de ressources
docker stats

# Augmenter la mémoire Docker
# Docker Desktop → Settings → Resources → Memory → 8GB minimum
```

#### Container qui crash
```bash
# Voir pourquoi il a crash
docker-compose logs <service>

# Voir les dernières lignes avant le crash
docker logs <container_id> --tail 100
```

### Réinitialisation complète

#### Soft reset (garder les données)
```bash
docker-compose down
docker-compose up -d
```

#### Hard reset (tout supprimer)
```bash
# Arrêter et supprimer tout
docker-compose down -v

# Nettoyer Docker complètement
docker system prune -a --volumes

# Redémarrer proprement
docker-compose up -d --build
```

### Problèmes de réseau

#### Containers ne communiquent pas
```bash
# Voir les réseaux
docker network ls

# Inspecter le réseau du projet
docker network inspect dandelion-grass_default

# Recréer les réseaux
docker-compose down
docker network prune
docker-compose up -d
```

### Problèmes de volumes

#### Voir les volumes
```bash
docker volume ls | grep mlopsdg
```

#### Supprimer un volume spécifique
```bash
docker volume rm mlopsdg_pg
docker volume rm mlopsdg_minio
docker volume rm mlopsdg_mlflow_data
```

#### Backup d'un volume
```bash
# Backup du volume MinIO
docker run --rm -v mlopsdg_minio:/data -v $(pwd):/backup alpine tar czf /backup/minio_backup.tar.gz /data

# Restore
docker run --rm -v mlopsdg_minio:/data -v $(pwd):/backup alpine tar xzf /backup/minio_backup.tar.gz -C /
```

---

## 🧪 Testing

### Test de l'API
```bash
# Smoke test
pytest tests/test_api_smoke.py

# Via docker
docker-compose exec api pytest tests/test_api_smoke.py -v
```

### Load testing avec Apache Bench
```bash
# 100 requêtes, 10 concurrentes
ab -n 100 -c 10 http://localhost:8000/healthz
```

### Tester tous les endpoints
```bash
# Health
curl http://localhost:8000/healthz

# Metrics
curl http://localhost:8000/metrics | head -20

# Docs (devrait retourner du HTML)
curl -I http://localhost:8000/docs
```

---

## 📊 Métriques et Monitoring

### Prometheus metrics
```bash
# Voir toutes les métriques
curl http://localhost:8000/metrics

# Filtrer une métrique spécifique
curl -s http://localhost:8000/metrics | grep api_requests_total
```

### Statistiques Docker
```bash
# Vue en temps réel
docker stats

# Une seule mesure
docker stats --no-stream
```

---

## 🎯 Commandes pour la Démo

### Scénario de démo complet
```bash
# 1. Vérifier que tout est UP
docker-compose ps

# 2. Ouvrir toutes les interfaces
open http://localhost:8000/docs  # API
open http://localhost:8501       # WebApp
open http://localhost:5001       # MLflow
open http://localhost:8080       # Airflow
open http://localhost:9001       # MinIO

# 3. Vérifier les données
docker-compose exec api python /workspace/scripts/seed_urls_to_db.py

# 4. Déclencher l'ingestion
docker-compose exec airflow airflow dags trigger ingest_images

# 5. Attendre 30s puis vérifier
docker-compose exec airflow airflow dags list-runs -d ingest_images | head -3

# 6. Lancer le training (dans un terminal dédié)
docker-compose exec airflow python3 -m ml.train_optimized

# 7. Recharger l'API
MODEL_URI=$(docker-compose exec api python3 << 'EOF'
import boto3, os
s3 = boto3.client("s3",
    endpoint_url=os.getenv("S3_ENDPOINT_URL"),
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"))
response = s3.list_objects_v2(Bucket='plants', Prefix='models/')
models = sorted(response['Contents'], key=lambda x: x['LastModified'], reverse=True)
print(f"s3://plants/{models[0]['Key']}")
EOF
)

curl -X POST "http://localhost:8000/admin/reload?model_s3_uri=${MODEL_URI}"

# 8. Tester une prédiction
curl -o /tmp/test.jpg "https://upload.wikimedia.org/wikipedia/commons/thumb/3/31/Dandelion-Taraxacum_officinale.jpg/320px-Dandelion-Taraxacum_officinale.jpg"
curl -X POST http://localhost:8000/predict -F "file=@/tmp/test.jpg" | jq
```

---

## 📝 Variables d'Environnement

### Voir les variables d'un service
```bash
docker-compose exec <service> env

# Exemple
docker-compose exec api env | grep MODEL
```

### Modifier temporairement une variable
```bash
# Dans docker-compose exec
docker-compose exec -e MODEL_PATH=/new/path api env | grep MODEL

# Redémarrer avec nouvelle variable
MODEL_PATH=/new/path docker-compose up -d api
```

---

## 🔑 Credentials par défaut

### Airflow
- URL: http://localhost:8080
- Username: `airflow`
- Password: `airflow`

### MinIO
- URL: http://localhost:9001
- Username: `minio`
- Password: `minio12345`

### PostgreSQL
- Host: `localhost`
- Port: `5432`
- Database: `plants`
- Username: `plants`
- Password: `plants`

### MLflow
- URL: http://localhost:5001
- No authentication (dev mode)

---

## 🆘 Commandes d'Urgence

### Tout tombe en prod
```bash
# 1. Logs rapides
docker-compose logs --tail=50 | grep -i error

# 2. Redémarrage rapide
docker-compose restart

# 3. Si ça ne marche pas
docker-compose down
docker-compose up -d

# 4. Si toujours pas
docker-compose down -v
docker-compose up -d --build
```

### API ne répond plus
```bash
# 1. Vérifier l'état
curl http://localhost:8000/healthz

# 2. Voir les logs
docker-compose logs api --tail=100

# 3. Redémarrer juste l'API
docker-compose restart api

# 4. Vérifier à nouveau
sleep 5
curl http://localhost:8000/healthz
```

### Espace disque plein
```bash
# 1. Voir l'utilisation
docker system df

# 2. Nettoyer les images non utilisées
docker image prune -a

# 3. Nettoyer tout (⚠️ attention)
docker system prune -a --volumes
```

---

## 📚 Raccourcis Utiles

### Alias à ajouter dans ~/.bashrc ou ~/.zshrc
```bash
# Raccourcis Docker Compose
alias dcu="docker-compose up -d"
alias dcd="docker-compose down"
alias dcl="docker-compose logs -f"
alias dcp="docker-compose ps"

# Raccourcis pour ce projet
alias mlops-start="cd /path/to/dandelion-grass && docker-compose --env-file compose.env up -d"
alias mlops-stop="cd /path/to/dandelion-grass && docker-compose down"
alias mlops-logs="cd /path/to/dandelion-grass && docker-compose logs -f"
alias mlops-train="docker-compose exec airflow python3 -m ml.train_optimized"
```

---

## 🎓 Tips & Tricks

### Commande multi-services
```bash
# Redémarrer plusieurs services
docker-compose restart api webapp mlflow

# Voir les logs de plusieurs services
docker-compose logs -f api airflow
```

### Watch mode pour monitoring
```bash
# Surveiller les containers
watch -n 2 'docker-compose ps'

# Surveiller les logs
watch -n 1 'docker-compose logs api --tail=20'
```

### Ouvrir un shell dans un container
```bash
# Bash
docker-compose exec api bash
docker-compose exec airflow bash

# Python
docker-compose exec api python3
docker-compose exec airflow python3
```

### Copier des fichiers
```bash
# Depuis le container vers l'hôte
docker cp mlopsdg-api-1:/tmp/model.pt ./local_model.pt

# Depuis l'hôte vers le container
docker cp ./local_file.txt mlopsdg-api-1:/tmp/
```

---

*Aide-mémoire créé pour faciliter les présentations et le dépannage*
*Dernière mise à jour: 2025-11-07*
