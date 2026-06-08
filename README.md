# ML-Ops Repository 🚀

Collection de projets MLOps opérationnels et templates réutilisables pour l'équipe.

## 📁 Projects

### 🌿 [Dandelion vs Grass](./projects/dandelion-grass/)
**Status**: ✅ **FULLY OPERATIONAL**

Pipeline MLOps complet implémenté avec :
- **Ingestion** : 100 images (50 dandelion + 50 grass) via Airflow
- **Entraînement** : ResNet18 avec 90% accuracy sur validation
- **Tracking** : MLflow avec métriques et artifacts S3
- **Déploiement** : FastAPI + Streamlit pour prédictions
- **Infrastructure** : Docker Compose multi-services

**Performance** : 90% accuracy | 0.496 loss | ~1min training time

## 🛠️ Templates

- `templates/docker-compose/` - Configurations Docker réutilisables
- `templates/airflow-dags/` - Templates de DAGs Airflow
- `templates/mlflow-configs/` - Configurations MLflow pour différents environnements

## 📚 Documentation

- `docs/MLOps-Best-Practices.md` - Bonnes pratiques MLOps
- `docs/Docker-Setup-Guide.md` - Guide de configuration Docker
- `docs/Troubleshooting.md` - Résolution de problèmes courants

## 🚀 Quick Start

1. **Cloner le repository** :
```bash
git clone https://github.com/CazenaveAlbertSchool/Bloc4
```

2. **Lancer un projet** :
```bash
cd projects/dandelion-grass
docker compose --env-file compose.env up -d --build
```

3. **Accéder aux interfaces** :
- **Streamlit** : http://localhost:8501
- **API** : http://localhost:8000/docs
- **MLflow** : http://localhost:5000
- **Airflow** : http://localhost:8080

## 👥 Team Collaboration

### Branches
- `main` : Production ready
- `develop` : Integration branch
- `feature/*` : Nouvelles fonctionnalités
- `hotfix/*` : Corrections urgentes

### Workflow
1. Créer une branche feature depuis `develop`
2. Développer et tester localement
3. Créer une Pull Request vers `develop`
4. Review et merge
5. Déployer sur `main` pour production

## 📊 Project Status

| Project | Status | Accuracy | Last Update |
|---------|--------|----------|-------------|
| Dandelion vs Grass | ✅ Operational | 90% | 2025-10-22 |

## 🔧 Troubleshooting

### Problèmes courants
- **MLflow "Invalid Host header"** : Configuré avec `--allowed-hosts "*"`
- **MinIO bucket missing** : Créé automatiquement au premier run
- **Airflow-MLflow connection** : Variables d'environnement configurées

### Support
Pour toute question ou problème, créer une issue sur GitHub.

---

**Maintenu par l'équipe MLOps** | **Dernière mise à jour** : 2026-06-08
