"""Scaler alignment decision (Milestone 3).

``docs/UPGRADE_ROADMAP.md`` asks to align the IsolationForest "healthy-only"
scaler with the XGBoost "full-dataset" scaler, *or to document the decision
not to*.

**Decision: do not unify them.** They are fitted on deliberately different
populations, and the difference is the whole point:

* ``models/scaler.joblib`` — fitted on the full training dataset, including
  failure flights, for the supervised classifier.
* the scaler bundled inside ``models/anomaly_detector.joblib`` — fitted on
  healthy flights only, so that "distance from normal" is meaningful.

Unifying them would replace the healthy-only reference distribution with one
contaminated by failure flights, which is exactly the signal the anomaly
detector exists to measure. They stay separate; they are kept dimensionally
compatible so the same feature vector can be scored by both.

Measured difference (2026-09-26): identical dimensionality (94 features), but
clearly different ``mean_``/``scale_`` statistics.
"""

import json

import joblib
import numpy as np

from src.diagnosis.anomaly_detector import AnomalyDetector
from src.runtime_paths import MODELS_DIR


def _classifier_scaler():
    return joblib.load(MODELS_DIR / "scaler.joblib")


def _anomaly_bundle_scaler():
    return joblib.load(MODELS_DIR / "anomaly_detector.joblib")["scaler"]


def _model_feature_columns() -> list[str]:
    return json.loads((MODELS_DIR / "feature_columns.json").read_text(encoding="utf-8"))


def test_anomaly_detector_uses_the_scaler_bundled_with_its_own_artifact():
    """It must score through its own healthy-only scaler, never the classifier's."""
    detector = AnomalyDetector()
    assert detector.available, detector.unavailable_reason
    bundle_scaler = _anomaly_bundle_scaler()
    assert np.allclose(detector.scaler.mean_, bundle_scaler.mean_)
    assert np.allclose(detector.scaler.scale_, bundle_scaler.scale_)


def test_anomaly_scaler_is_not_the_classifier_scaler():
    """The two scalers encode different reference populations."""
    classifier_scaler = _classifier_scaler()
    anomaly_scaler = _anomaly_bundle_scaler()
    assert not np.allclose(anomaly_scaler.mean_, classifier_scaler.mean_)
    assert not np.allclose(anomaly_scaler.scale_, classifier_scaler.scale_)


def test_both_scalers_share_the_model_feature_dimensionality():
    """They differ statistically but stay dimensionally interchangeable."""
    expected = len(_model_feature_columns())
    assert _classifier_scaler().n_features_in_ == expected
    assert _anomaly_bundle_scaler().n_features_in_ == expected


def test_anomaly_feature_sidecar_matches_the_model_schema():
    """The anomaly sidecar must stay aligned with the main schema, or scoring
    falls back to an exact-dimension match and can silently stop working."""
    anomaly_columns = json.loads(
        (MODELS_DIR / "anomaly_feature_columns.json").read_text(encoding="utf-8")
    )
    assert len(anomaly_columns) == len(_model_feature_columns())
    assert _anomaly_bundle_scaler().n_features_in_ == len(anomaly_columns)
