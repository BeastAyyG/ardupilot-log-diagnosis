import os
import json
import numpy as np

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


class MLClassifier:
    """Trained ML model for failure classification."""

    def __init__(
        self,
        model_dir: str = "models/",
        min_probability: float = DEFAULT_PROB_THRESHOLD,
    ):
        self.model_path = os.path.join(model_dir, "classifier.joblib")
        self.scaler_path = os.path.join(model_dir, "scaler.joblib")
        self.features_path = os.path.join(model_dir, "feature_columns.json")
        self.labels_path = os.path.join(model_dir, "label_columns.json")
        self.min_probability = float(min_probability)
        self.label_thresholds = dict(LABEL_PROB_THRESHOLDS)

        self.available = False
        if joblib is None:
            return

        if os.path.exists(self.model_path) and os.path.exists(self.scaler_path):
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
                self.available = True
            except Exception:
                self.available = False

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

        vibe_clip_total = float(features.get("vibe_clip_total", 0.0))
        vibe_x = float(features.get("vibe_x_max", 0.0))
        vibe_y = float(features.get("vibe_y_max", 0.0))
        vibe_z = float(features.get("vibe_z_max", 0.0))
        vibe_peak = max(vibe_x, vibe_y, vibe_z)

        mag_range = float(features.get("mag_field_range", 0.0))
        mag_std = float(features.get("mag_field_std", 0.0))

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

    def predict(self, features: dict) -> list:
        if not self.available:
            return []

        from src.diagnosis.failure_types import FAILURE_RECOMMENDATIONS

        vector = []
        for feat in self.feature_columns:
            vector.append(float(features.get(feat, 0.0)))

        X = np.array(vector).reshape(1, -1)
        X_scaled = self.scaler.transform(X)

        probas = self.model.predict_proba(X_scaled)

        diagnoses = []
        label_probs = {}
        if isinstance(probas, list):
            for i, label in enumerate(self.label_columns):
                prob = float(probas[i][0, 1]) if probas[i].shape[1] > 1 else 0.0
                label_probs[label] = prob
                if prob >= self._threshold_for_label(label):
                    diagnoses.append(
                        self._build_diagnosis(label, prob, FAILURE_RECOMMENDATIONS)
                    )
        else:
            for i, label in enumerate(self.label_columns):
                prob = float(probas[0, i])
                label_probs[label] = prob
                if prob >= self._threshold_for_label(label):
                    diagnoses.append(
                        self._build_diagnosis(label, prob, FAILURE_RECOMMENDATIONS)
                    )

        diagnoses = self._contextual_compass_vibration_filter(
            features,
            diagnoses,
            label_probs,
            FAILURE_RECOMMENDATIONS,
        )

        diagnoses.sort(key=lambda x: x["confidence"], reverse=True)
        return diagnoses[:MAX_PREDICTED_LABELS]

    def get_feature_importance(self) -> dict:
        return {}
