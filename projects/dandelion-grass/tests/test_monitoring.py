"""
Tests unitaires pour monitoring/drift_check.py

Utilise des DataFrames synthétiques — pas besoin de Postgres, MinIO ni Evidently
réseau. Les tests vérifient la logique de détection de drift et les cas limites.
"""

import json
import os
import sys
import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql://plants:plants@localhost:5432/plants")

# ── Fixtures ──────────────────────────────────────────────────────

FEATURE_COLS = ["confidence", "mean_r", "mean_g", "mean_b", "brightness"]


def _make_df(n: int, label: str = "grass", shift: float = 0.0,
             seed: int = 42) -> pd.DataFrame:
    """Generate a synthetic predictions DataFrame."""
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "ts":         pd.date_range("2024-01-01", periods=n, freq="10min"),
        "label":      [label] * n,
        "confidence": np.clip(rng.normal(0.85 + shift, 0.08, n), 0, 1),
        "mean_r":     rng.normal(80  + shift * 50, 15, n),
        "mean_g":     rng.normal(150 + shift * 50, 20, n),
        "mean_b":     rng.normal(60  + shift * 50, 12, n),
        "brightness": rng.normal(96  + shift * 50, 18, n),
    })


def _make_stable_pair(n: int = 100):
    """Reference and current from the same distribution — no drift expected."""
    ref = _make_df(n, seed=1)
    cur = _make_df(n, seed=2)  # same params, different seed
    return ref[FEATURE_COLS], cur[FEATURE_COLS]


def _make_drifted_pair(n: int = 100, shift: float = 1.5):
    """Current heavily shifted vs reference — drift expected."""
    ref = _make_df(n, shift=0.0, seed=1)
    cur = _make_df(n, shift=shift, seed=2)
    return ref[FEATURE_COLS], cur[FEATURE_COLS]


# ── Tests : logique Evidently (intégration légère) ────────────────

class TestDriftCheckLogic:
    """
    Ces tests importent directement les primitives Evidently
    sans dépendances réseau.
    """

    def test_no_drift_on_identical_distribution(self):
        from evidently.metrics import DatasetDriftMetric
        from evidently.report import Report

        ref, cur = _make_stable_pair(n=200)

        report = Report(metrics=[DatasetDriftMetric()])
        report.run(reference_data=ref, current_data=cur)
        result = report.as_dict()["metrics"][0]["result"]

        # Same distribution → drift_detected should be False
        assert result["dataset_drift"] is False

    def test_drift_detected_on_large_shift(self):
        from evidently.metrics import DatasetDriftMetric
        from evidently.report import Report

        ref, cur = _make_drifted_pair(n=200, shift=3.0)

        report = Report(metrics=[DatasetDriftMetric()])
        report.run(reference_data=ref, current_data=cur)
        result = report.as_dict()["metrics"][0]["result"]

        assert result["dataset_drift"] is True
        assert result["share_of_drifted_columns"] > 0

    def test_share_drifted_columns_is_between_0_and_1(self):
        from evidently.metrics import DatasetDriftMetric
        from evidently.report import Report

        ref, cur = _make_drifted_pair(n=150, shift=1.0)
        report = Report(metrics=[DatasetDriftMetric()])
        report.run(reference_data=ref, current_data=cur)
        share = report.as_dict()["metrics"][0]["result"]["share_of_drifted_columns"]

        assert 0.0 <= share <= 1.0


# ── Tests : run_drift_check (avec mocks réseau) ───────────────────

class TestRunDriftCheck:

    @patch("monitoring.drift_check._push_drift_score_to_api")
    @patch("monitoring.drift_check._upload_to_s3")
    @patch("monitoring.drift_check._get_current_df")
    @patch("monitoring.drift_check._get_reference_df")
    def test_returns_ok_with_sufficient_data(
        self, mock_ref, mock_cur, mock_upload, mock_push
    ):
        from monitoring.drift_check import run_drift_check

        mock_ref.return_value = _make_df(100, seed=1)
        mock_cur.return_value = _make_df(100, seed=2)
        mock_upload.return_value = None
        mock_push.return_value = None

        result = run_drift_check()

        assert result["status"] == "ok"
        assert "drift_score" in result
        assert "drift_detected" in result
        assert "n_reference" in result
        assert "n_current" in result
        assert 0.0 <= result["drift_score"] <= 1.0

    @patch("monitoring.drift_check._get_current_df")
    @patch("monitoring.drift_check._get_reference_df")
    def test_returns_insufficient_data_when_too_few_rows(self, mock_ref, mock_cur):
        from monitoring.drift_check import run_drift_check

        mock_ref.return_value = _make_df(100, seed=1)
        mock_cur.return_value = _make_df(5, seed=2)  # below MIN_ROWS=30

        result = run_drift_check()
        assert result["status"] == "insufficient_data"

    @patch("monitoring.drift_check._push_drift_score_to_api")
    @patch("monitoring.drift_check._upload_to_s3")
    @patch("monitoring.drift_check._get_current_df")
    @patch("monitoring.drift_check._get_reference_df")
    def test_push_score_is_called_on_success(
        self, mock_ref, mock_cur, mock_upload, mock_push
    ):
        from monitoring.drift_check import run_drift_check

        mock_ref.return_value = _make_df(100, seed=1)
        mock_cur.return_value = _make_df(100, seed=2)
        mock_upload.return_value = None

        run_drift_check()

        mock_push.assert_called_once()
        score_arg = mock_push.call_args[0][0]
        assert 0.0 <= score_arg <= 1.0

    @patch("monitoring.drift_check._get_current_df")
    @patch("monitoring.drift_check._get_reference_df")
    def test_drift_detected_on_heavily_shifted_data(self, mock_ref, mock_cur):
        from monitoring.drift_check import run_drift_check

        with patch("monitoring.drift_check._upload_to_s3"), \
             patch("monitoring.drift_check._push_drift_score_to_api"):

            mock_ref.return_value = _make_df(200, shift=0.0, seed=1)
            mock_cur.return_value = _make_df(200, shift=3.0, seed=2)

            result = run_drift_check()

        assert result["status"] == "ok"
        assert result["drift_detected"] is True
        assert result["drift_score"] > 0.0


# ── Tests : image feature extraction (API) ───────────────────────

class TestExtractFeatures:

    def test_extract_features_returns_four_keys(self):
        import os
        os.environ.setdefault("DATABASE_URL", "")
        from apps.api.main import _extract_features
        from PIL import Image

        img = Image.new("RGB", (224, 224), color=(100, 150, 80))
        feats = _extract_features(img)

        assert set(feats.keys()) == {"mean_r", "mean_g", "mean_b", "brightness"}

    def test_extract_features_values_in_range(self):
        from apps.api.main import _extract_features
        from PIL import Image

        img = Image.new("RGB", (224, 224), color=(200, 100, 50))
        feats = _extract_features(img)

        for key, val in feats.items():
            assert 0.0 <= val <= 255.0, f"{key} = {val} out of [0, 255]"

    def test_brightness_is_mean_of_channels(self):
        from apps.api.main import _extract_features
        from PIL import Image

        img = Image.new("RGB", (64, 64), color=(120, 180, 60))
        feats = _extract_features(img)

        expected_brightness = (feats["mean_r"] + feats["mean_g"] + feats["mean_b"]) / 3.0
        assert abs(feats["brightness"] - expected_brightness) < 0.01
