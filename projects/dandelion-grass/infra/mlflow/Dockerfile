FROM ghcr.io/mlflow/mlflow:latest

USER root
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir psycopg2-binary

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Créer le répertoire pour la DB et donner les permissions
RUN mkdir -p /mlflow && chown -R 1000:1000 /mlflow

USER 1000

EXPOSE 5000

ENTRYPOINT ["/entrypoint.sh"]

