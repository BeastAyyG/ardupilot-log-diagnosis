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

    def __init__(self, model_dir: str = "models/", min_probability: float = DEFAULT_PROB_THRESHOLD):
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
                self.model = joblib.load(self.model_path)
                self.scaler = joblib.load(self.scaler_path)
                with open(self.features_path, 'r') as f:
                    self.feature_columns = json.load(f)
                with open(self.labels_path, 'r') as f:
                    self.label_columns = json.load(f)
                self.available = True
            except Exception:
                self.available = False

    def _threshold_for_label(self, label: str) -> float:
        return float(self.label_thresholds.get(label, self.min_probability))

    def _build_diagnosis(self, label: str, prob: float, failure_recommendations: dict) -> dict:
        return {
            "failure_type": label,
            "confidence": prob,
            "severity": "critical" if prob > 0.85 else "warning",
            "detection_method": "ml",
            "evidence": [{"feature": "ML prediction", "value": prob, "threshold": self._threshold_for_label(label), "direction": "above"}],
            "recommendation": failure_recommendations.get(label, "Review log mechanically."),
        }

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
        if isinstance(probas, list):
            for i, label in enumerate(self.label_columns):
                prob = float(probas[i][0, 1]) if probas[i].shape[1] > 1 else 0.0
                if prob >= self._threshold_for_label(label):
                    diagnoses.append(self._build_diagnosis(label, prob, FAILURE_RECOMMENDATIONS))
        else:
            for i, label in enumerate(self.label_columns):
                prob = float(probas[0, i])
                if prob >= self._threshold_for_label(label):
                    diagnoses.append(self._build_diagnosis(label, prob, FAILURE_RECOMMENDATIONS))

        diagnoses.sort(key=lambda x: x["confidence"], reverse=True)
        return diagnoses[:MAX_PREDICTED_LABELS]

    def get_feature_importance(self) -> dict:
        return {}
