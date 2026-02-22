from .rule_engine import RuleEngine
from .ml_classifier import MLClassifier
from typing import Optional

class HybridEngine:
    """Combines RuleEngine + MLClassifier results."""
    
    def __init__(self, rule_engine: Optional[RuleEngine] = None, ml_classifier: Optional[MLClassifier] = None):
        self.rules = rule_engine or RuleEngine()
        self.ml = ml_classifier or MLClassifier()
        
    def diagnose(self, features: dict) -> list:
        rule_results = self.rules.diagnose(features)
        ml_results = self.ml.predict(features) if self.ml.available else []
        
        rule_dict = {d["failure_type"]: d for d in rule_results}
        ml_dict = {d["failure_type"]: d for d in ml_results}
        
        all_types = set(rule_dict.keys()).union(set(ml_dict.keys()))
        
        merged_diagnoses = []
        from .failure_types import FAILURE_RECOMMENDATIONS
        
        for ftype in all_types:
            rule_conf = rule_dict[ftype]["confidence"] if ftype in rule_dict else 0.0
            ml_prob = ml_dict[ftype]["confidence"] if ftype in ml_dict else 0.0
            
            evidence = []
            if ftype in rule_dict:
                evidence.extend(rule_dict[ftype].get("evidence", []))
            if ftype in ml_dict and ftype not in rule_dict:
                evidence.extend(ml_dict[ftype].get("evidence", []))
                
            if rule_conf > 0 and ml_prob > 0:
                final = 0.7 * ml_prob + 0.3 * rule_conf + 0.05
                method = "rule+ml"
            elif ml_prob > 0:
                final = ml_prob * 0.8
                method = "ml"
            elif rule_conf > 0:
                final = rule_conf * 0.85
                method = "rule"
            else:
                continue
                
            if final < 0.25:
                continue
                
            severity = "critical" if final > 0.6 else ("warning" if final > 0.3 else "info")
            
            merged_diagnoses.append({
                "failure_type": ftype,
                "confidence": min(float(final), 1.0),
                "severity": severity,
                "detection_method": method,
                "evidence": evidence,
                "recommendation": FAILURE_RECOMMENDATIONS.get(ftype, "Review log mechanically.")
            })
            
        merged_diagnoses.sort(key=lambda x: x["confidence"], reverse=True)
        
        # Filter: keep the highest confidence, only keep others if confidence > 0.4 
        # to prevent symptom cascading (e.g. vibration causing compass warnings)
        if merged_diagnoses:
            filtered_diagnoses = [merged_diagnoses[0]]
            for d in merged_diagnoses[1:]:
                if d["confidence"] > 0.4:
                    filtered_diagnoses.append(d)
            return filtered_diagnoses
            
        return []
