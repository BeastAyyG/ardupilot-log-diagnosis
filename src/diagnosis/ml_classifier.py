import os
import json
import numpy as np
import joblib

class MLClassifier:
    """Trained ML model for failure classification."""
    
    def __init__(self, model_dir: str = "models/"):
        self.model_path = os.path.join(model_dir, "classifier.joblib")
        self.scaler_path = os.path.join(model_dir, "scaler.joblib")
        self.features_path = os.path.join(model_dir, "feature_columns.json")
        self.labels_path = os.path.join(model_dir, "label_columns.json")
        
        self.available = False
        if os.path.exists(self.model_path) and os.path.exists(self.scaler_path):
            try:
                self.model = joblib.load(self.model_path)
                self.scaler = joblib.load(self.scaler_path)
                with open(self.features_path, 'r') as f:
                    self.feature_columns = json.load(f)
                with open(self.labels_path, 'r') as f:
                    self.label_columns = json.load(f)
                self.available = True
            except Exception as e:
                self.available = False

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
                if prob > 0.3:
                    diagnoses.append({
                        "failure_type": label,
                        "confidence": prob,
                        "severity": "critical" if prob > 0.8 else "warning",
                        "detection_method": "ml",
                        "evidence": [{"feature": "ML prediction", "value": prob, "threshold": 0.3, "direction": "above"}],
                        "recommendation": FAILURE_RECOMMENDATIONS.get(label, "Review log mechanically.")
                    })
        else:
            for i, label in enumerate(self.label_columns):
                prob = float(probas[0, i])
                if prob > 0.3:
                    diagnoses.append({
                        "failure_type": label,
                        "confidence": prob,
                        "severity": "critical" if prob > 0.8 else "warning",
                        "detection_method": "ml",
                        "evidence": [{"feature": "ML prediction", "value": prob, "threshold": 0.3, "direction": "above"}],
                        "recommendation": FAILURE_RECOMMENDATIONS.get(label, "Review log mechanically.")
                    })
                    
        diagnoses.sort(key=lambda x: x["confidence"], reverse=True)
        return diagnoses

    def get_feature_importance(self) -> dict:
        return {}
