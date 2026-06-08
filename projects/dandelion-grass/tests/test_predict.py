"""
Tests du endpoint /predict et des endpoints de monitoring.

Utilise des images synthétiques PIL — pas besoin de MinIO, Postgres ni modèle réel.
"""

import io
import os
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

os.environ.setdefault("DATABASE_URL", "")
os.environ.setdefault("MODEL_PATH", "")
os.environ.setdefault("MODEL_S3_URI", "")
os.environ.setdefault("S3_ENDPOINT_URL", "http://localhost:9000")

from apps.api.main import app  # noqa: E402  (env must be set first)

client = TestClient(app)


# ── Helpers ──────────────────────────────────────────────────────

def _make_image(color: tuple = (80, 160, 80), size: tuple = (224, 224)) -> bytes:
    """Create a solid-colour JPEG in memory."""
    img = Image.new("RGB", size, color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return buf.getvalue()


def _make_yellow_image() -> bytes:
    """Bright yellow image — heuristic predicts 'dandelion'."""
    img = Image.new("RGB", (224, 224), color=(240, 220, 50))
    draw = ImageDraw.Draw(img)
    # Add a rough circle to simulate a flower
    draw.ellipse([50, 50, 174, 174], fill=(255, 230, 0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return buf.getvalue()


# ── /healthz ─────────────────────────────────────────────────────

def test_healthz_returns_ok():
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_healthz_contains_model_flag():
    r = client.get("/healthz")
    assert "model" in r.json()


# ── /predict ─────────────────────────────────────────────────────

def test_predict_returns_200_with_valid_image():
    img_bytes = _make_image()
    r = client.post("/predict", files={"file": ("test.jpg", img_bytes, "image/jpeg")})
    assert r.status_code == 200


def test_predict_response_shape():
    img_bytes = _make_image()
    r = client.post("/predict", files={"file": ("test.jpg", img_bytes, "image/jpeg")})
    body = r.json()
    assert "label" in body
    assert "prob" in body
    assert "version" in body
    assert "source" in body


def test_predict_label_is_valid_class():
    img_bytes = _make_image()
    r = client.post("/predict", files={"file": ("test.jpg", img_bytes, "image/jpeg")})
    assert r.json()["label"] in ("grass", "dandelion")


def test_predict_probability_in_range():
    img_bytes = _make_image()
    r = client.post("/predict", files={"file": ("test.jpg", img_bytes, "image/jpeg")})
    prob = r.json()["prob"]
    assert 0.0 <= prob <= 1.0


def test_predict_heuristic_green_is_grass():
    """Pure green image should lean towards grass in the heuristic fallback."""
    img_bytes = _make_image(color=(30, 180, 30))
    r = client.post("/predict", files={"file": ("test.jpg", img_bytes, "image/jpeg")})
    assert r.status_code == 200
    # heuristic: grass when green dominates over yellow-score
    assert r.json()["label"] == "grass"


def test_predict_heuristic_yellow_is_dandelion():
    """Bright yellow image should lean towards dandelion in heuristic."""
    img_bytes = _make_yellow_image()
    r = client.post("/predict", files={"file": ("test.jpg", img_bytes, "image/jpeg")})
    assert r.status_code == 200
    assert r.json()["label"] == "dandelion"


def test_predict_rejects_non_image():
    r = client.post("/predict", files={"file": ("bad.txt", b"not an image", "text/plain")})
    assert r.status_code == 400


def test_predict_different_sizes_accepted():
    for size in [(32, 32), (128, 128), (512, 512)]:
        img_bytes = _make_image(size=size)
        r = client.post("/predict", files={"file": ("img.jpg", img_bytes, "image/jpeg")})
        assert r.status_code == 200, f"Failed for size {size}"


# ── /metrics ─────────────────────────────────────────────────────

def test_metrics_endpoint_returns_prometheus_format():
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "api_requests_total" in r.text


def test_metrics_request_counter_increments():
    before_r = client.get("/metrics")
    before_count = _parse_counter(before_r.text, "api_requests_total")

    img_bytes = _make_image()
    client.post("/predict", files={"file": ("img.jpg", img_bytes, "image/jpeg")})

    after_r = client.get("/metrics")
    after_count = _parse_counter(after_r.text, "api_requests_total")

    assert after_count > before_count


def _parse_counter(metrics_text: str, name: str) -> float:
    """Extract the value of a Prometheus counter from text format."""
    for line in metrics_text.splitlines():
        if line.startswith(name) and not line.startswith("#"):
            return float(line.split()[-1])
    return 0.0


# ── /admin/drift-score ────────────────────────────────────────────

def test_drift_score_endpoint_accepts_valid_score():
    r = client.post("/admin/drift-score", params={"score": 0.25, "drift_detected": "false"})
    assert r.status_code == 200
    assert r.json()["drift_score"] == pytest.approx(0.25)


def test_drift_score_endpoint_rejects_score_above_1():
    r = client.post("/admin/drift-score", params={"score": 1.5})
    assert r.status_code == 422


def test_drift_score_reflected_in_prometheus_gauge():
    client.post("/admin/drift-score", params={"score": 0.42, "drift_detected": "true"})
    r = client.get("/metrics")
    assert "model_drift_score" in r.text
    gauge_val = _parse_counter(r.text, "model_drift_score")
    assert gauge_val == pytest.approx(0.42, abs=1e-3)
