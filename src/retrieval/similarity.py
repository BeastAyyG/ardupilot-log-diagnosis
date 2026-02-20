import json
import os
import numpy as np
from scipy.spatial.distance import cosine
from src.constants import FEATURE_NAMES

class FailureRetrieval:
    """Match new logs against database of known failures."""
    
    def __init__(self, known_failures_path: str = "models/known_failures.json"):
        self.known_failures_path = known_failures_path
        self.known = self._load()
        self.scaler = None
        
    def _load(self):
        if os.path.exists(self.known_failures_path):
            try:
                with open(self.known_failures_path, 'r') as f:
                    return json.load(f)
            except Exception:
                return {"failures": []}
        return {"failures": []}
        
    def _save(self):
        os.makedirs(os.path.dirname(self.known_failures_path), exist_ok=True)
        with open(self.known_failures_path, 'w') as f:
            json.dump(self.known, f, indent=2)

    def find_similar(self, features: dict, top_k: int = 3) -> list:
        if not self.known.get("failures"): return []
            
        vector = np.array([float(features.get(k, 0.0)) for k in FEATURE_NAMES])
        norm_v = np.linalg.norm(vector)
        if norm_v == 0: return []
        
        results = []
        for case in self.known["failures"]:
            k_feats = case.get("features", {})
            k_vector = np.array([float(k_feats.get(k, 0.0)) for k in FEATURE_NAMES])
            norm_k = np.linalg.norm(k_vector)
            
            if norm_k == 0: continue
            
            # cosine can throw warning or error if vectors are zero but we checked norm
            try:
                sim = 1.0 - cosine(vector, k_vector)
            except Exception:
                sim = 0.0
                
            if sim > 0.5:
                results.append({
                    "similarity": float(sim),
                    "failure_type": case.get("failure_type", "unknown"),
                    "source_url": case.get("source_url", ""),
                    "root_cause": case.get("root_cause", ""),
                    "fix": case.get("fix", "")
                })
                
        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:top_k]

    def add_known_failure(self, features: dict, failure_type: str,
                          source_url: str = "", root_cause: str = "", fix: str = ""):
        case = {
            "id": f"known_{len(self.known.get('failures', [])) + 1:03d}",
            "failure_type": failure_type,
            "source_url": source_url,
            "root_cause": root_cause,
            "fix": fix,
            "features": {k: float(features.get(k, 0.0)) for k in FEATURE_NAMES}
        }
        if "failures" not in self.known:
            self.known["failures"] = []
        self.known["failures"].append(case)
        self._save()
