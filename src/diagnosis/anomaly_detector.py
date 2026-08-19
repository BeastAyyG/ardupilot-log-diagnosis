from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np

from src.runtime_paths import MODELS_DIR

class AnomalyDetector:
    """Autoencoder-based anomaly detection trained on healthy flights.

    The detector learns the distribution of normal flight telemetry.
    When a new log's features deviate significantly from the learned
    normal distribution, it flags an anomaly.

    This approach requires ZERO failure data — only healthy flights.
    """

    def __init__(self, model_path: str | os.PathLike[str] | None = None):
        resolved_model_path = (
            Path(model_path) if model_path is not None else MODELS_DIR / "anomaly_detector.joblib"
        )
        self.model_path = str(resolved_model_path)
        self.feature_schema_path = str(
            resolved_model_path.with_name("anomaly_feature_columns.json")
        )
        self.feature_columns: list[str] = []
        self.feature_schema_source = "unavailable"
        self.unavailable_reason = "anomaly artifacts not loaded"
        self.available = False
        self._load()

    def _load(self):
        try:
            import joblib
            bundle = joblib.load(self.model_path)
            # Support both Autoencoder and Isolation Forest
            if "encoder" in bundle and "decoder" in bundle:
                self.encoder = bundle["encoder"]
                self.decoder = bundle["decoder"]
                self.scaler = bundle["scaler"]
                self.threshold = bundle["threshold"]  # 95th percentile of training errors
                self.model_type = "autoencoder"
            elif "iso_forest" in bundle:
                self.iso_forest = bundle["iso_forest"]
                self.scaler = bundle["scaler"]
                self.model_type = "isolation_forest"
            else:
                raise ValueError("Unknown model bundle format")
            expected_count = int(getattr(self.scaler, "n_features_in_", 0))
            bundle_columns = bundle.get("feature_columns")
            if isinstance(bundle_columns, list) and all(
                isinstance(name, str) for name in bundle_columns
            ) and len(bundle_columns) == expected_count:
                self.feature_columns = list(bundle_columns)
                self.feature_schema_source = "artifact_bundle"
            else:
                schema_path = Path(self.feature_schema_path)
                if schema_path.exists():
                    with schema_path.open(encoding="utf-8") as handle:
                        sidecar_columns = json.load(handle)
                    if not (
                        isinstance(sidecar_columns, list)
                        and all(isinstance(name, str) for name in sidecar_columns)
                        and len(sidecar_columns) == expected_count
                    ):
                        raise ValueError(
                            "anomaly feature sidecar is not a valid ordered schema"
                        )
                    self.feature_columns = list(sidecar_columns)
                    self.feature_schema_source = "artifact_sidecar"
                else:
                    # Legacy artifacts did not retain their schema.  They may
                    # still be scored only when the caller supplies an exact
                    # dimensional match; never pad/truncate a feature vector.
                    self.feature_schema_source = "caller_exact_dimension"
            self.available = True
            self.unavailable_reason = "available"
        except Exception as exc:
            self.unavailable_reason = f"failed to load anomaly artifacts: {exc}"
            self.available = False

    def score(self, features: dict, feature_columns: list) -> dict:
        """Compute anomaly score for a feature vector.

        Returns:
            {
                "anomaly_score": float,     # 0.0 = perfectly normal
                "is_anomaly": bool,         # True if score > threshold
                "top_deviations": list,     # which features deviated most
            }
        """
        if not self.available:
            return {
                "anomaly_score": 0.0,
                "is_anomaly": False,
                "top_deviations": [],
                "unavailable_reason": self.unavailable_reason,
            }

        def _safe_float(value):
            try:
                numeric_value = float(value)
            except (TypeError, ValueError, OverflowError):
                return 0.0
            return numeric_value if np.isfinite(numeric_value) else 0.0

        columns = list(getattr(self, "feature_columns", [])) or list(feature_columns)
        expected_count = int(getattr(self.scaler, "n_features_in_", len(columns)))
        if len(columns) != expected_count:
            reason = (
                "anomaly feature schema does not match artifact dimensionality "
                f"({len(columns)} != {expected_count})"
            )
            self.unavailable_reason = reason
            return {
                "anomaly_score": 0.0,
                "is_anomaly": False,
                "top_deviations": [],
                "unavailable_reason": reason,
            }

        vector = np.array([_safe_float(features.get(f, 0.0)) for f in columns])

        # We need to reshape for sklearn/keras
        try:
            X = self.scaler.transform(vector.reshape(1, -1))
        except ValueError as exc:
            reason = f"anomaly scaler rejected feature vector: {exc}"
            self.unavailable_reason = reason
            return {
                "anomaly_score": 0.0,
                "is_anomaly": False,
                "top_deviations": [],
                "unavailable_reason": reason,
            }

        if self.model_type == "autoencoder":
            # Encode → Decode → measure reconstruction error
            encoded = self.encoder.predict(X, verbose=0)
            reconstructed = self.decoder.predict(encoded, verbose=0)
            errors = np.abs(X[0] - reconstructed[0])

            anomaly_score = float(np.mean(errors))
            is_anomaly = anomaly_score > self.threshold

            # Find which features contributed most to the anomaly
            top_indices = np.argsort(errors)[-5:][::-1]
            top_deviations = [
                {"feature": columns[i], "error": float(errors[i])}
                for i in top_indices
            ]

            return {
                "anomaly_score": anomaly_score,
                "is_anomaly": is_anomaly,
                "top_deviations": top_deviations,
                "feature_schema_source": getattr(
                    self, "feature_schema_source", "caller_exact_dimension"
                ),
            }

        elif self.model_type == "isolation_forest":
            # predict returns 1 for inliers, -1 for outliers
            # decision_function returns anomaly score (negative for anomalies)
            score = float(self.iso_forest.decision_function(X)[0])
            is_anomaly = self.iso_forest.predict(X)[0] == -1

            # Isolation forest doesn't directly give feature contributions
            # We can proxy it by looking at normalized absolute deviation from mean
            deviations = np.abs(X[0]) # X is already scaled, so 0 is mean
            top_indices = np.argsort(deviations)[-5:][::-1]
            top_deviations = [
                {"feature": columns[i], "error": float(deviations[i])}
                for i in top_indices
            ]

            # Invert score so higher = more anomalous (for consistency)
            return {
                "anomaly_score": -score,
                "is_anomaly": bool(is_anomaly),
                "top_deviations": top_deviations,
                "feature_schema_source": getattr(
                    self, "feature_schema_source", "caller_exact_dimension"
                ),
            }

        return {
            "anomaly_score": 0.0,
            "is_anomaly": False,
            "top_deviations": [],
            "unavailable_reason": "unknown anomaly model type",
        }
