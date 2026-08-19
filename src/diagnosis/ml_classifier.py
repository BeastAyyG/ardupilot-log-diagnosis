import os
import json
import hashlib
import numpy as np
from typing import Any, cast
from src.constants import FEATURE_NAMES, VALID_LABELS
from src.contracts import DiagnosisDict, FeatureDict
from src.runtime_paths import MODELS_DIR, resolve_repo_path

try:
    import joblib
except Exception:
    joblib = None


DEFAULT_PROB_THRESHOLD = 0.55
LABEL_PROB_THRESHOLDS = {
    "vibration_high": 0.55,
    "compass_interference": 0.55,
    "gps_quality_poor": 0.60,
    "power_instability": 0.62,
    "ekf_failure": 0.65,
    "motor_imbalance": 0.68,
    "mechanical_failure": 0.72,
    "crash_unknown": 0.80,
}
MAX_PREDICTED_LABELS = 3
DEFAULT_INFERENCE_WINDOW_CONFIG = {
    "version": 1,
    "window_sec": 5.0,
    "overlap": 0.5,
    "include_full_log": True,
    "aggregation": "max_raw_probability",
    "source": "legacy_default_unverified",
    "verified": False,
}


class MLClassifier:
    """Trained ML model for failure classification."""

    def __init__(
        self,
        model_dir: str | os.PathLike[str] | None = None,
        min_probability: float = DEFAULT_PROB_THRESHOLD,
    ):
        resolved_model_dir = resolve_repo_path(model_dir) if model_dir is not None else MODELS_DIR
        self.model_path = str(resolved_model_dir / "classifier.joblib")
        self.scaler_path = str(resolved_model_dir / "scaler.joblib")
        self.features_path = str(resolved_model_dir / "feature_columns.json")
        self.labels_path = str(resolved_model_dir / "label_columns.json")
        self.manifest_path = str(resolved_model_dir / "manifest.json")
        self.min_probability = float(min_probability)
        self.label_thresholds = dict(LABEL_PROB_THRESHOLDS)
        self.unavailable_reason = "ml artifacts not loaded"
        self.unsupported_labels: list[str] = list(VALID_LABELS)
        self.inference_window_config = dict(DEFAULT_INFERENCE_WINDOW_CONFIG)

        self.available = False
        if joblib is None:
            self.unavailable_reason = "joblib unavailable"
            return

        required_paths = [
            self.model_path,
            self.scaler_path,
            self.features_path,
            self.labels_path,
            self.manifest_path,
        ]
        if all(os.path.exists(path) for path in required_paths):
            try:
                loaded_model = joblib.load(self.model_path)
                if isinstance(loaded_model, dict) and "model" in loaded_model:
                    self.model = loaded_model["model"]
                else:
                    self.model = loaded_model

                self.scaler = joblib.load(self.scaler_path)
                with open(self.features_path, "r") as f:
                    self.feature_columns = json.load(f)
                with open(self.labels_path, "r") as f:
                    self.label_columns = json.load(f)
                self.unsupported_labels = sorted(
                    set(VALID_LABELS) - set(self.label_columns)
                )
                with open(self.manifest_path, "r") as f:
                    self.manifest = json.load(f)
                self.inference_window_config = self._load_inference_window_config()
                self.available = self._manifest_matches_runtime()
                if self.available and self.unsupported_labels:
                    self.unavailable_reason = (
                        "available; rules-only labels: "
                        + ", ".join(self.unsupported_labels)
                    )
                else:
                    self.unavailable_reason = (
                        "available" if self.available else "manifest schema mismatch"
                    )
            except Exception as exc:
                self.unavailable_reason = f"failed to load ml artifacts: {exc}"
                self.available = False
        else:
            self.unavailable_reason = "missing classifier, scaler, schema, or manifest artifact"

    def _hash_json_list(self, values: list[str]) -> str:
        payload = json.dumps(values, sort_keys=True).encode()
        return hashlib.sha256(payload).hexdigest()

    def _hash_threshold_config(self) -> str:
        model_dir = os.path.dirname(self.model_path)
        threshold_path = os.path.join(model_dir, "rule_thresholds.yaml")
        if not os.path.exists(threshold_path):
            return ""
        with open(threshold_path, "r") as file_obj:
            return hashlib.sha256(file_obj.read().encode()).hexdigest()

    def _load_inference_window_config(self) -> dict[str, Any]:
        configured = getattr(self, "manifest", {}).get("inference_window", {})
        if not isinstance(configured, dict):
            return dict(DEFAULT_INFERENCE_WINDOW_CONFIG)
        try:
            window_sec = float(configured["window_sec"])
            overlap = float(configured["overlap"])
            if window_sec <= 0 or not 0 <= overlap < 1:
                raise ValueError
        except (KeyError, TypeError, ValueError):
            return dict(DEFAULT_INFERENCE_WINDOW_CONFIG)
        return {
            "version": int(configured.get("version", 1)),
            "window_sec": window_sec,
            "overlap": overlap,
            "include_full_log": bool(configured.get("include_full_log", True)),
            "aggregation": str(configured.get("aggregation", "max_raw_probability")),
            "source": "artifact_manifest",
            "verified": True,
        }

    def get_inference_window_config(self) -> dict[str, Any]:
        """Return an immutable-by-convention copy of the model window contract."""
        return dict(self.inference_window_config)

    def _manifest_matches_runtime(self) -> bool:
        manifest = getattr(self, "manifest", {})
        model_features = list(getattr(self, "feature_columns", []))
        runtime_features = set(FEATURE_NAMES)
        # A model may intentionally be trained on a stable subset while the
        # runtime pipeline gains additional rule-only features. Keep that
        # backwards-compatible, but never allow a model to request unknown
        # features or a scaler with the wrong dimensionality.
        model_schema_ok = (
            bool(model_features)
            and set(model_features).issubset(runtime_features)
            and len(model_features) == int(getattr(self.scaler, "n_features_in_", len(model_features)))
            and manifest.get("feature_schema_hash") == self._hash_json_list(model_features)
        )
        labels_are_known = bool(self.label_columns) and set(self.label_columns).issubset(VALID_LABELS)
        trained_label_hash = self._hash_json_list(list(self.label_columns))
        # Artifact schema v2 records the actual trained label columns. Older
        # artifacts stored the broader runtime schema hash; accept them only
        # as explicit legacy subsets so production output remains transparent.
        manifest_label_hash = manifest.get("trained_label_schema_hash")
        if manifest_label_hash is None and manifest.get("artifact_schema_version") is None:
            labels_match_artifact = (
                manifest.get("label_schema_hash") == self._hash_json_list(VALID_LABELS)
            )
        else:
            labels_match_artifact = (
                manifest_label_hash == trained_label_hash
                and manifest.get("runtime_label_schema_hash")
                == self._hash_json_list(VALID_LABELS)
            )
        return (
            model_schema_ok
            and labels_are_known
            and labels_match_artifact
            and manifest.get("threshold_config_hash", "") == self._hash_threshold_config()
        )

    def _threshold_for_label(self, label: str) -> float:
        return float(self.label_thresholds.get(label, self.min_probability))

    def _build_diagnosis(
        self, label: str, prob: float, failure_recommendations: dict
    ) -> dict:
        return {
            "failure_type": label,
            "confidence": prob,
            "severity": "critical" if prob > 0.85 else "warning",
            "detection_method": "ml",
            "evidence": [
                {
                    "feature": "ML prediction",
                    "value": prob,
                    "threshold": self._threshold_for_label(label),
                    "direction": "above",
                }
            ],
            "recommendation": failure_recommendations.get(
                label, "Review log mechanically."
            ),
        }

    def _contextual_compass_vibration_filter(
        self,
        features: dict,
        diagnoses: list,
        label_probs: dict,
        failure_recommendations: dict,
    ) -> list:
        if not diagnoses:
            return []

        diag_by_label = {d["failure_type"]: d for d in diagnoses}
        has_vibration = "vibration_high" in diag_by_label
        has_compass = "compass_interference" in diag_by_label

        def _f(key, default=0.0):
            v = features.get(key, default)
            return float(v if v is not None else default)

        vibe_clip_total = _f("vibe_clip_total")
        vibe_x = _f("vibe_x_max")
        vibe_y = _f("vibe_y_max")
        vibe_z = _f("vibe_z_max")
        vibe_peak = max(vibe_x, vibe_y, vibe_z)

        mag_range = _f("mag_field_range")
        mag_std = _f("mag_field_std")

        likely_compass_context = (
            vibe_clip_total <= 0
            and vibe_peak < 65.0
            and mag_range > 320.0
            and mag_std > 35.0
        )
        likely_vibration_context = vibe_clip_total > 100 or vibe_peak > 80.0

        if has_vibration and has_compass:
            if likely_compass_context and not likely_vibration_context:
                diag_by_label.pop("vibration_high", None)
            elif likely_vibration_context:
                diag_by_label.pop("compass_interference", None)
        elif has_vibration and likely_compass_context:
            diag_by_label.pop("vibration_high", None)
            compass_prob = float(label_probs.get("compass_interference", 0.0))
            compass_conf = max(compass_prob, 0.35)
            diag_by_label["compass_interference"] = {
                "failure_type": "compass_interference",
                "confidence": compass_conf,
                "severity": "warning",
                "detection_method": "ml+context",
                "evidence": [
                    {
                        "feature": "context_compass_override",
                        "value": {
                            "vibe_clip_total": vibe_clip_total,
                            "vibe_peak": vibe_peak,
                            "mag_field_range": mag_range,
                            "mag_field_std": mag_std,
                            "model_prob": compass_prob,
                        },
                        "threshold": "clip=0 & vibe<65 & mag_range>320 & mag_std>35",
                        "direction": "context",
                    }
                ],
                "recommendation": failure_recommendations.get(
                    "compass_interference", "Review log mechanically."
                ),
            }

        out = list(diag_by_label.values())
        out.sort(key=lambda x: x["confidence"], reverse=True)
        return out

    @staticmethod
    def _safe_feature_value(value: Any) -> float:
        try:
            numeric = float(value)
        except (TypeError, ValueError, OverflowError):
            return 0.0
        return numeric if np.isfinite(numeric) else 0.0

    def _feature_matrix(self, feature_sets: list[FeatureDict]) -> np.ndarray:
        return np.asarray(
            [
                [self._safe_feature_value(features.get(name, 0.0)) for name in self.feature_columns]
                for features in feature_sets
            ],
            dtype=float,
        )

    def _predict_probability_rows(self, feature_sets: list[FeatureDict]) -> np.ndarray:
        """Return raw class probabilities in model label order for every feature set."""
        if not self.available or not feature_sets:
            return np.empty((0, len(getattr(self, "label_columns", []))), dtype=float)

        matrix = self._feature_matrix(feature_sets)
        scaled = self.scaler.transform(matrix)
        probabilities = cast(Any, self.model).predict_proba(scaled)
        if isinstance(probabilities, list):
            columns = []
            for probability in probabilities:
                array = np.asarray(probability, dtype=float)
                columns.append(array[:, 1] if array.ndim == 2 and array.shape[1] > 1 else np.zeros(len(matrix)))
            return np.column_stack(columns)
        return np.asarray(probabilities, dtype=float)

    def score_features(self, features: FeatureDict) -> dict[str, float]:
        """Expose raw class probabilities for one complete feature vector."""
        rows = self._predict_probability_rows([features])
        if not len(rows):
            return {}
        return {
            label: float(rows[0, index])
            for index, label in enumerate(self.label_columns)
        }

    def _diagnoses_from_probabilities(
        self, label_probs: dict[str, float], context_features: FeatureDict
    ) -> list[DiagnosisDict]:
        from src.diagnosis.failure_types import FAILURE_RECOMMENDATIONS

        diagnoses = [
            self._build_diagnosis(label, probability, FAILURE_RECOMMENDATIONS)
            for label, probability in label_probs.items()
            if probability >= self._threshold_for_label(label)
        ]
        diagnoses = self._contextual_compass_vibration_filter(
            context_features,
            diagnoses,
            label_probs,
            FAILURE_RECOMMENDATIONS,
        )
        diagnoses.sort(key=lambda item: item["confidence"], reverse=True)
        return diagnoses[:MAX_PREDICTED_LABELS]

    def predict(self, features: FeatureDict) -> list[DiagnosisDict]:
        """Diagnose one full-log feature vector without temporal aggregation."""
        label_probs = self.score_features(features)
        self.last_prediction_info = {"aggregation": "full_log", "candidate_count": 1}
        return self._diagnoses_from_probabilities(label_probs, features)

    def predict_windows(
        self,
        feature_windows: list[FeatureDict],
        context_features: FeatureDict | None = None,
    ) -> list[DiagnosisDict]:
        """Aggregate raw ML probabilities exactly as the training log-level metric does."""
        if not self.available:
            return []
        if not feature_windows:
            return self.predict(context_features or {})

        probability_rows = self._predict_probability_rows(feature_windows)
        if not len(probability_rows):
            return []
        peak_indices = np.argmax(probability_rows, axis=0)
        peak_probabilities = np.max(probability_rows, axis=0)
        label_probs = {
            label: float(peak_probabilities[index])
            for index, label in enumerate(self.label_columns)
        }
        diagnoses = self._diagnoses_from_probabilities(
            label_probs, context_features or feature_windows[0]
        )
        for diagnosis in diagnoses:
            label_index = self.label_columns.index(diagnosis["failure_type"])
            feature_window = feature_windows[int(peak_indices[label_index])]
            window_metadata = feature_window.get("_metadata", {})
            diagnosis["evidence"].append(
                {
                    "feature": "ml_peak_window",
                    "value": {
                        "candidate_index": int(peak_indices[label_index]),
                        "window_start_sec": window_metadata.get("window_start"),
                        "window_end_sec": window_metadata.get("window_end"),
                    },
                    "threshold": "maximum raw class probability across candidates",
                    "direction": "max",
                }
            )
        self.last_prediction_info = {
            "aggregation": "max_raw_probability",
            "candidate_count": len(feature_windows),
            "peak_window_index_by_label": {
                label: int(peak_indices[index])
                for index, label in enumerate(self.label_columns)
            },
        }
        return diagnoses

    def get_feature_importance(self) -> dict:
        if not self.available or not hasattr(self.model, "feature_importances_"):
            return {}

        importances = getattr(self.model, "feature_importances_", None)
        if importances is None:
            return {}

        try:
            return {
                feature: float(score)
                for feature, score in zip(self.feature_columns, importances, strict=False)
            }
        except TypeError:
            return {
                feature: float(score)
                for feature, score in zip(self.feature_columns, importances)
            }
