from typing import Optional, cast

from .anomaly_detector import AnomalyDetector
from .ml_classifier import MLClassifier
from .rule_engine import RuleEngine
from src.contracts import DiagnosisDict, FeatureDict


MIN_MERGED_CONFIDENCE = 0.45
SECONDARY_MIN_CONFIDENCE = 0.70
SECONDARY_MAX_GAP = 0.10
MAX_HYBRID_DIAGNOSES = 2

METHOD_PRIORITY = {"rule+ml": 2, "ml": 1, "rule": 0}
LABEL_PRIORITY = {
    "vibration_high": 5,
    "compass_interference": 5,
    "motor_imbalance": 5,
    "mechanical_failure": 6,
    "thrust_loss": 6,
    "gps_quality_poor": 4,
    "power_instability": 4,
    "brownout": 4,
    "ekf_failure": 4,
    "pid_tuning_issue": 3,
    "rc_failsafe": 2,
    "crash_unknown": 1,
}


class HybridEngine:
    """Combines RuleEngine + AnomalyDetector + MLClassifier results."""

    def __init__(
        self,
        rule_engine: Optional[RuleEngine] = None,
        ml_classifier: Optional[MLClassifier] = None,
        anomaly_detector: Optional[AnomalyDetector] = None,
    ):
        self.rules = rule_engine or RuleEngine()
        self.ml = ml_classifier or MLClassifier()
        self.anomaly_detector = anomaly_detector or AnomalyDetector()

    def diagnose(self, features: FeatureDict) -> list[DiagnosisDict]:
        rule_results = self.rules.diagnose(features)
        ml_results = self.ml.predict(features) if self.ml.available else []
        anomaly_info = {"is_anomaly": False, "anomaly_score": 0.0}

        has_rule = len(rule_results) > 0
        if (
            self.anomaly_detector.available
            and self.ml.available
            and hasattr(self.ml, "feature_columns")
        ):
            anomaly_info = self.anomaly_detector.score(features, self.ml.feature_columns)
            if not anomaly_info["is_anomaly"] and not has_rule:
                ml_results = []

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
                final = rule_conf * 0.85
                method = "rule"
            else:
                continue

            if final < MIN_MERGED_CONFIDENCE:
                continue

            severity = "critical" if final > 0.6 else ("warning" if final > 0.3 else "info")
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

        def tanomaly_key_for(ftype: str) -> str | None:
            mapping = {
                "vibration_high": "vibe_z_tanomaly",
                "compass_interference": "mag_tanomaly",
                "power_instability": "volt_tanomaly",
                "gps_quality_poor": "gps_hdop_tanomaly",
                "motor_imbalance": "motor_spread_tanomaly",
                "mechanical_failure": "motor_spread_tanomaly",
                "thrust_loss": "_thrust_loss_tanomaly",
                "ekf_failure": "ekf_pos_var_tanomaly",
                "rc_failsafe": "rc_failsafe_tanomaly",
                "pid_tuning_issue": "pid_sat_tanomaly",
            }
            return mapping.get(ftype)

        def tanomaly_for(ftype: str) -> float:
            key = tanomaly_key_for(ftype)
            if not key:
                return -1.0
            try:
                return float(features.get(key, -1.0))
            except (TypeError, ValueError):
                return -1.0

        def build_hypotheses() -> list[dict]:
            hypotheses = []
            for ftype in sorted(all_types):
                rule_conf = rule_dict[ftype]["confidence"] if ftype in rule_dict else 0.0
                ml_conf = ml_dict[ftype]["confidence"] if ftype in ml_dict else 0.0
                evidence = []
                if ftype in rule_dict:
                    evidence.extend(rule_dict[ftype].get("evidence", []))
                if ftype in ml_dict and ftype not in rule_dict:
                    evidence.extend(ml_dict[ftype].get("evidence", []))
                lead = evidence[0] if evidence else {}
                hypotheses.append(
                    {
                        "failure_type": ftype,
                        "source": (
                            "rule+ml"
                            if rule_conf > 0 and ml_conf > 0
                            else ("rule" if rule_conf > 0 else "ml")
                        ),
                        "rule_confidence": float(rule_conf),
                        "ml_confidence": float(ml_conf),
                        "merged_confidence": next(
                            (
                                float(diag["confidence"])
                                for diag in merged_diagnoses
                                if diag["failure_type"] == ftype
                            ),
                            max(float(rule_conf), float(ml_conf)),
                        ),
                        "tanomaly": tanomaly_for(ftype),
                        "lead_feature": lead.get("feature"),
                        "lead_value": lead.get("value"),
                    }
                )
            hypotheses.sort(
                key=lambda item: (
                    item["tanomaly"] if item["tanomaly"] > 0 else float("inf"),
                    -item["merged_confidence"],
                )
            )
            return hypotheses

        def set_explain(final_diagnoses: list[DiagnosisDict], arbiter: dict | None = None) -> None:
            self.last_explain_data = {
                "rule": rule_results,
                "ml": ml_results,
                "anomaly": anomaly_info,
                "hypotheses": build_hypotheses(),
                "causal_arbiter": arbiter or {},
                "final": final_diagnoses,
            }

        if merged_diagnoses and len(merged_diagnoses) > 1:
            timed_candidates = []
            for diag in merged_diagnoses:
                tanomaly = tanomaly_for(diag["failure_type"])
                if tanomaly > 0:
                    timed_candidates.append((tanomaly, diag["confidence"], diag))

            if timed_candidates:
                temporal_tie_window_us = 5_000_000
                temporal_proximity_us = 30_000_000
                extreme_confidence = 0.85

                timed_candidates.sort(key=lambda item: (item[0], -item[1]))
                best_time, best_conf, best_diag = timed_candidates[0]
                root_cause = best_diag

                for event_time, event_conf, event_diag in timed_candidates[1:]:
                    time_gap = event_time - best_time
                    if time_gap <= temporal_tie_window_us and event_conf > best_conf:
                        root_cause = event_diag
                        best_conf = event_conf
                    elif (
                        time_gap <= temporal_proximity_us
                        and event_conf >= extreme_confidence
                        and event_conf > best_conf + 0.15
                    ):
                        root_cause = event_diag
                        best_conf = event_conf

                root_cause = dict(root_cause)
                root_cause["recommendation"] = "[ARB] " + str(
                    root_cause.get("recommendation", "")
                )
                selected = [cast(DiagnosisDict, root_cause)]
                for diag in merged_diagnoses:
                    if diag["failure_type"] == root_cause["failure_type"]:
                        continue
                    is_critical_rule = (
                        diag["detection_method"] == "rule"
                        and diag["severity"] == "critical"
                    )
                    if is_critical_rule:
                        selected.append(diag)
                    if len(selected) >= MAX_HYBRID_DIAGNOSES:
                        break

                arbiter = {
                    "selected_failure_type": root_cause["failure_type"],
                    "selected_tanomaly": best_time,
                    "reason": "earliest onset candidate selected by temporal arbitration",
                }
                if len(timed_candidates) > 1:
                    second_time, _, second_diag = timed_candidates[1]
                    arbiter["reason"] = (
                        f"{root_cause['failure_type']} preceded "
                        f"{second_diag['failure_type']} by {(second_time - best_time) / 1e6:.1f}s"
                    )
                set_explain(selected, arbiter)
                return selected

        if merged_diagnoses:
            primary = merged_diagnoses[0]
            filtered_diagnoses = [primary]
            for diag in merged_diagnoses[1:]:
                is_critical_rule = (
                    diag["detection_method"] == "rule"
                    and diag["severity"] == "critical"
                )
                is_nearby_rule_signal = (
                    diag["detection_method"] == "rule"
                    and diag["confidence"] >= MIN_MERGED_CONFIDENCE
                    and (primary["confidence"] - diag["confidence"]) <= SECONDARY_MAX_GAP
                )
                if is_critical_rule or is_nearby_rule_signal:
                    filtered_diagnoses.append(diag)
                elif (
                    diag["confidence"] >= SECONDARY_MIN_CONFIDENCE
                    and (primary["confidence"] - diag["confidence"]) <= SECONDARY_MAX_GAP
                ):
                    filtered_diagnoses.append(diag)
                if len(filtered_diagnoses) >= MAX_HYBRID_DIAGNOSES:
                    break

            set_explain(
                filtered_diagnoses,
                {
                    "selected_failure_type": primary["failure_type"],
                    "selected_tanomaly": tanomaly_for(primary["failure_type"]),
                    "reason": "selected by merged confidence after arbitration filters",
                },
            )
            return filtered_diagnoses

        set_explain([], {"reason": "no rule or ml diagnosis crossed thresholds"})
        return []
