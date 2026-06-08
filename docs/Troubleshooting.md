# Troubleshooting Guide

## 🐛 Problèmes Courants

### 1. MLflow "Invalid Host header" Error

**Symptôme** :
```
mlflow.exceptions.MlflowException: API request to endpoint failed with error code 403 != 200. 
Response body: 'Invalid Host header - possible DNS rebinding attack detected'
```

**Solution** :
```bash
# Dans docker-compose.yml, ajouter à MLflow :
environment:
  SERVER_NAME: ""
  WERKZEUG_DEBUG_PIN: "off"

# Dans infra/mlflow/entrypoint.sh :
exec mlflow server \
  --allowed-hosts "*" \
  --host 0.0.0.0 \
  --port 5000
```

### 2. MinIO Bucket Missing

**Symptôme** :
```
RuntimeError: Not enough images ingested yet. Please run ingestion first.
```

**Solution** :
```bash
# Créer le bucket manuellement
docker compose exec minio mc mb local/plants

# Ou vérifier la configuration dans docker-compose.yml
environment:
  MINIO_DEFAULT_BUCKETS: plants
```

### 3. Airflow Database Connection Error

**Symptôme** :
```
airflow.exceptions.AirflowConfigException: error: cannot use SQLite with the LocalExecutor
```

**Solution** :
```bash
# Dans docker-compose.yml, configurer PostgreSQL :
environment:
  AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: postgresql+psycopg2://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
```

### 4. Port Already in Use

**Symptôme** :
```
Error response from daemon: ports are not available: exposing port TCP 0.0.0.0:8501
```

**Solution** :
```bash
# Arrêter tous les conteneurs
docker compose down

# Vérifier les ports utilisés
lsof -i :8501

# Redémarrer
docker compose up -d --build
```

### 5. Module Not Found in Airflow

**Symptôme** :
```
ModuleNotFoundError: No module named 'ml'
```

**Solution** :
```bash
# Dans docker-compose.yml, ajouter volumes et PYTHONPATH :
volumes:
  - ./ml:/opt/airflow/ml
  - ./scripts:/opt/airflow/scripts
environment:
  PYTHONPATH: /opt/airflow:/opt/airflow/dags
```

## 🔍 Debugging

### Logs des Services

```bash
# Logs spécifiques
docker compose logs mlflow
docker compose logs airflow
docker compose logs api

# Logs en temps réel
docker compose logs -f

# Logs avec timestamps
docker compose logs -t
```

### Vérification État des Services

```bash
# État des conteneurs
docker compose ps

# Santé des services
docker compose exec postgres pg_isready
docker compose exec minio mc admin info local
curl http://localhost:5000/health
```

### Accès aux Conteneurs

```bash
# Shell dans un conteneur
docker compose exec airflow bash
docker compose exec mlflow bash
docker compose exec api bash

# Exécution de commandes
docker compose exec api python scripts/seed_urls_to_db.py
docker compose exec airflow airflow dags list
```

## 🛠️ Maintenance

### Nettoyage Docker

```bash
# Supprimer les conteneurs arrêtés
docker container prune

# Supprimer les images inutilisées
docker image prune

# Supprimer les volumes inutilisés
docker volume prune

# Nettoyage complet
docker system prune -a
```

### Reset Complet

```bash
# Arrêter et supprimer tout
docker compose down -v

# Supprimer les images
docker compose down --rmi all

# Redémarrer proprement
docker compose up -d --build
```

### Sauvegarde des Données

```bash
# Sauvegarder PostgreSQL
docker compose exec postgres pg_dump -U postgres plants > backup.sql

# Sauvegarder MinIO
docker compose exec minio mc mirror local/plants /backup/plants

# Restaurer
docker compose exec postgres psql -U postgres plants < backup.sql
```

## 📊 Monitoring

### Métriques de Performance

```bash
# Utilisation des ressources
docker stats

# Espace disque
df -h

# Mémoire
free -h

# Processus
top
```

### Vérification des Endpoints

```bash
# API Health
curl http://localhost:8000/health

# MLflow Health
curl http://localhost:5000/health

# MinIO Health
curl http://localhost:9001/minio/health/live

# Airflow Health
curl http://localhost:8080/health
```

## 🚨 Alertes

### Seuils Critiques
- **CPU Usage** > 80%
- **Memory Usage** > 85%
- **Disk Usage** > 90%
- **API Latency** > 2s
- **Error Rate** > 5%

### Actions Automatiques
- Redémarrage automatique des services
- Scaling horizontal Kubernetes
- Notification Slack/Email
- Rollback automatique

---

**Pour plus d'aide, créer une issue sur GitHub** 🆘


