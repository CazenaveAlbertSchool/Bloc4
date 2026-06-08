FROM apache/airflow:2.9.3-python3.11
USER airflow
RUN pip install --no-cache-dir boto3 pillow psycopg2-binary requests torch torchvision tqdm mlflow \
    evidently==0.4.36 pandas==2.2.2
ENTRYPOINT []
CMD ["bash", "-c", "airflow db migrate && (airflow users create --username airflow --password airflow --firstname Airflow --lastname Admin --role Admin --email admin@example.com || true) && airflow scheduler & airflow webserver"]
