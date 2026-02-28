from .rule_engine import RuleEngine
from .ml_classifier import MLClassifier
from typing import Optional


MIN_MERGED_CONFIDENCE = 0.45
SECONDARY_MIN_CONFIDENCE = 0.70
SECONDARY_MAX_GAP = 0.08
MAX_HYBRID_DIAGNOSES = 2

METHOD_PRIORITY = {"rule+ml": 2, "ml": 1, "rule": 0}
LABEL_PRIORITY = {
    "vibration_high": 5,
    "compass_interference": 5,
    "gps_quality_poor": 4,
    "power_instability": 4,
    "brownout": 4,
    "ekf_failure": 3,
    "motor_imbalance": 3,
    "pid_tuning_issue": 3,
    "mechanical_failure": 2,
    "rc_failsafe": 2,
    "crash_unknown": 1,
}


class HybridEngine:
    """Combines RuleEngine + MLClassifier results."""

    def __init__(
        self,
        rule_engine: Optional[RuleEngine] = None,
        ml_classifier: Optional[MLClassifier] = None,
    ):
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
                final = 0.65 * ml_prob + 0.35 * rule_conf
                method = "rule+ml"
            elif ml_prob > 0:
                final = ml_prob * 0.85
                method = "ml"
            elif rule_conf > 0:
                final = rule_conf * 0.75
                method = "rule"
            else:
                continue

            if final < MIN_MERGED_CONFIDENCE:
                continue

            severity = (
                "critical" if final > 0.6 else ("warning" if final > 0.3 else "info")
            )

            merged_diagnoses.append(
                {
                    "failure_type": ftype,
                    "confidence": min(float(final), 1.0),
                    "severity": severity,
                    "detection_method": method,
                    "evidence": evidence,
                    "recommendation": FAILURE_RECOMMENDATIONS.get(
                        ftype, "Review log mechanically."
                    ),
                    "reason_code": "confirmed" if final >= 0.7 else "uncertain",
                }
            )

        def rank(diag: dict) -> tuple:
            return (
                float(diag.get("confidence", 0.0)),
                METHOD_PRIORITY.get(diag.get("detection_method", ""), 0),
                LABEL_PRIORITY.get(diag.get("failure_type", ""), 0),
            )

        merged_diagnoses.sort(key=rank, reverse=True)

        # Temporal Arbiter Filter (Phase 3 Integration)
        # Disambiguate root cause by selecting the earliest onset symptom.
        # Only filter when we have multiple candidates and at least one has valid tanomaly data.
        if merged_diagnoses and len(merged_diagnoses) > 1:
            prefix_map = {
                "vibration_high": "vibe_z",
                "compass_interference": "mag",
                "power_instability": "volt",
                "gps_quality_poor": "gps_hdop",
                "motor_imbalance": "motor_spread",
                "ekf_failure": "ekf_pos_var",
            }

            # Build (tanomaly, confidence, diag) tuples for candidates with valid tanomaly
            timed_candidates = []
            for d in merged_diagnoses:
                ftype = d["failure_type"]
                prefix = prefix_map.get(ftype)
                tanomaly = features.get(f"{prefix}_tanomaly", -1.0) if prefix else -1.0
                if tanomaly > 0:
                    timed_candidates.append((tanomaly, d["confidence"], d))

            if timed_candidates:
                # Sort by earliest onset, then by confidence for ties within 5 seconds
                TEMPORAL_TIE_WINDOW_US = 5_000_000  # 5 seconds
                timed_candidates.sort(key=lambda x: (x[0], -x[1]))

                best_time, best_conf, best_diag = timed_candidates[0]
                root_cause = best_diag

                # Within tie window, prefer the higher confidence label
                for t_time, t_conf, t_diag in timed_candidates[1:]:
                    if (
                        t_time - best_time <= TEMPORAL_TIE_WINDOW_US
                        and t_conf > best_conf
                    ):
                        root_cause = t_diag
                        best_conf = t_conf

                root_cause = dict(root_cause)  # don't mutate original
                root_cause["recommendation"] = "[ARB] " + str(
                    root_cause.get("recommendation", "")
                )
                return [root_cause]

        # Filter for low-quality symptom cascades if Temporal Arbiter didn't trigger
        if merged_diagnoses:
            primary = merged_diagnoses[0]
            filtered_diagnoses = [primary]
            for d in merged_diagnoses[1:]:
                if (
                    d["confidence"] >= SECONDARY_MIN_CONFIDENCE
                    and (primary["confidence"] - d["confidence"]) <= SECONDARY_MAX_GAP
                    and d["detection_method"] != "rule"
                ):
                    filtered_diagnoses.append(d)
                if len(filtered_diagnoses) >= MAX_HYBRID_DIAGNOSES:
                    break
            return filtered_diagnoses

        return []
