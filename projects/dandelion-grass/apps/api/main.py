import io, os, time, threading, tempfile
from typing import Optional
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.responses import PlainTextResponse, JSONResponse
from PIL import Image
import psycopg2
import boto3
import torch
import torchvision.transforms as T
from prometheus_client import CollectorRegistry, Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

app = FastAPI(title="Dandelion vs Grass API", version="1.0.0")

# --- Metrics ---
registry = CollectorRegistry()
REQS = Counter("api_requests_total", "Total API requests", registry=registry)
LAT = Histogram("api_latency_seconds", "API latency", registry=registry)
PRED_LABEL = Counter("api_prediction_label_total", "Predictions by label", ["label"], registry=registry)
PRED_CONF = Histogram("api_prediction_confidence", "Prediction confidence", registry=registry)
DRIFT_SCORE = Gauge("model_drift_score", "Latest Evidently drift score (share of drifted columns)", registry=registry)
_last_drift_score: float = 0.0

# --- DB ---
DATABASE_URL = os.getenv("DATABASE_URL")

def get_conn():
    return psycopg2.connect(DATABASE_URL) if DATABASE_URL else None

def _init_db():
    conn = get_conn()
    if conn is None:
        return
    with conn, conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS predictions (
                id          SERIAL PRIMARY KEY,
                ts          TIMESTAMPTZ DEFAULT NOW(),
                label       TEXT,
                confidence  FLOAT,
                mean_r      FLOAT,
                mean_g      FLOAT,
                mean_b      FLOAT,
                brightness  FLOAT,
                source      TEXT
            )
        """)
    conn.close()

def _log_prediction(label: str, confidence: float, features: dict, source: str):
    conn = get_conn()
    if conn is None:
        return
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO predictions (label, confidence, mean_r, mean_g, mean_b, brightness, source)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (label, confidence, features["mean_r"], features["mean_g"],
                 features["mean_b"], features["brightness"], source),
            )
    finally:
        conn.close()

def _extract_features(img: Image.Image) -> dict:
    small = img.resize((32, 32))
    px = list(small.getdata())
    n = len(px)
    mean_r = sum(p[0] for p in px) / n
    mean_g = sum(p[1] for p in px) / n
    mean_b = sum(p[2] for p in px) / n
    return {"mean_r": mean_r, "mean_g": mean_g, "mean_b": mean_b,
            "brightness": (mean_r + mean_g + mean_b) / 3.0}

# --- S3/MinIO ---
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "http://minio:9000")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "minio")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "minio12345")
S3_BUCKET = os.getenv("S3_BUCKET", "plants")
s3 = boto3.client(
    "s3",
    endpoint_url=S3_ENDPOINT_URL,
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
)

# --- Model state ---
MODEL_PATH = os.getenv("MODEL_PATH", "./ml/dummy_model.pt")
MODEL_S3_URI = os.getenv("MODEL_S3_URI", "")
class_map = ["grass", "dandelion"]
preprocess = T.Compose([
    T.Resize((224,224)),
    T.ToTensor(),
    T.Normalize(mean=[0.485,0.456,0.406], std=[0.229,0.224,0.225]),
])

_model_lock = threading.Lock()
_model = None

def _parse_s3_uri(uri: str):
    assert uri.startswith("s3://")
    bucket_key = uri[len("s3://"):]
    parts = bucket_key.split("/", 1)
    bucket = parts[0]
    key = parts[1] if len(parts) > 1 else ""
    return bucket, key

def _load_model_from_path(path: str):
    m = torch.jit.load(path, map_location="cpu") if path.endswith(".pt") else torch.load(path, map_location="cpu")
    m.eval()
    return m

def _download_s3_to_tmp(uri: str) -> str:
    bucket, key = _parse_s3_uri(uri)
    fd, tmp_path = tempfile.mkstemp(suffix=os.path.splitext(key)[1] or ".pt")
    os.close(fd)
    s3.download_file(bucket, key, tmp_path)
    return tmp_path

def load_model(initial=False, uri: Optional[str]=None):
    global _model
    with _model_lock:
        use_uri = uri or MODEL_S3_URI
        if use_uri:
            tmp = _download_s3_to_tmp(use_uri)
            _model = _load_model_from_path(tmp)
        elif os.path.exists(MODEL_PATH):
            _model = _load_model_from_path(MODEL_PATH)
        else:
            _model = None
        if initial:
            print("Model loaded:", bool(_model))

def predict_tensor(img: Image.Image):
    if _model is None:
        # fallback heuristic
        px = img.resize((64, 64)).getdata()
        r = sum(p[0] for p in px) / (64*64)
        g = sum(p[1] for p in px) / (64*64)
        b = sum(p[2] for p in px) / (64*64)
        score = (r + g) / (b + 1e-5)
        prob = max(0.0, min(1.0, (score - 1.0) / 4.0))
        label = "dandelion" if prob > 0.5 else "grass"
        return label, float(prob), "heuristic"
    x = preprocess(img).unsqueeze(0)
    with torch.no_grad():
        logits = _model(x)
        prob = torch.softmax(logits, dim=1)[0]
        p_val, idx = torch.max(prob, dim=0)
    return class_map[idx.item()], float(p_val.item()), "model"

@app.on_event("startup")
def _startup():
    _init_db()
    load_model(initial=True)

@app.get("/healthz")
def healthz():
    return {"status": "ok", "model": bool(_model)}

@app.get("/metrics")
def metrics():
    data = generate_latest(registry)
    return PlainTextResponse(data.decode("utf-8"), media_type=CONTENT_TYPE_LATEST)

@app.post("/predict")
def predict(file: UploadFile = File(...)):
    start = time.time()
    REQS.inc()
    try:
        raw = file.file.read()
        img = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid image")
    label, prob, src = predict_tensor(img)
    LAT.observe(time.time() - start)
    # Async-safe: log in background to avoid blocking the response
    features = _extract_features(img)
    threading.Thread(target=_log_prediction, args=(label, prob, features, src), daemon=True).start()
    PRED_LABEL.labels(label=label).inc()
    PRED_CONF.observe(prob)
    return {"label": label, "prob": prob, "version": app.version, "source": src}

@app.post("/admin/reload")
def admin_reload(model_s3_uri: Optional[str] = Query(default=None)):
    """Hot-reload model from provided S3 URI or env MODEL_S3_URI"""
    if model_s3_uri:
        load_model(uri=model_s3_uri)
        return {"ok": True, "using": model_s3_uri}
    load_model()
    return {"ok": True, "using": MODEL_S3_URI or MODEL_PATH}

@app.post("/admin/drift-score")
def update_drift_score(score: float = Query(..., ge=0.0, le=1.0), drift_detected: bool = Query(default=False)):
    """Called by the Airflow monitoring DAG after each Evidently run."""
    global _last_drift_score
    DRIFT_SCORE.set(score)
    _last_drift_score = score
    return {"ok": True, "drift_score": score, "drift_detected": drift_detected}

@app.get("/monitoring/drift")
def get_drift():
    """Return latest drift metrics from the predictions table."""
    conn = get_conn()
    if conn is None:
        return JSONResponse({"error": "no database"}, status_code=503)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM predictions WHERE ts >= NOW() - INTERVAL '7 days'")
            n_recent = cur.fetchone()[0]
            cur.execute("SELECT label, COUNT(*) FROM predictions WHERE ts >= NOW() - INTERVAL '7 days' GROUP BY label")
            label_dist = {row[0]: row[1] for row in cur.fetchall()}
            cur.execute("SELECT AVG(confidence), MIN(confidence), MAX(confidence) FROM predictions WHERE ts >= NOW() - INTERVAL '7 days'")
            row = cur.fetchone()
            conf_stats = {"avg": row[0], "min": row[1], "max": row[2]} if row[0] is not None else {}
        return {
            "n_predictions_last_7d": n_recent,
            "label_distribution": label_dist,
            "confidence_stats": conf_stats,
            "drift_score": _last_drift_score,
        }
    finally:
        conn.close()
