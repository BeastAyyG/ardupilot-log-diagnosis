from typing import List, Optional

from .failure_types import FAILURE_RECOMMENDATIONS
from .rule_engine import RuleEngine
from .ml_classifier import MLClassifier


MIN_MERGED_CONFIDENCE = 0.45
SECONDARY_MIN_CONFIDENCE = 0.70
SECONDARY_MAX_GAP = 0.08
MAX_HYBRID_DIAGNOSES = 2

METHOD_PRIORITY = {"rule+ml": 2, "ml": 1, "rule": 0}
LABEL_PRIORITY = {
    "vibration_high":      5,
    "compass_interference": 5,
    "motor_imbalance":     5,   # Raised: motor failure is equally safety-critical
    "mechanical_failure":  6,   # Above motor_imbalance: specific root cause vs symptom
    "gps_quality_poor":    4,
    "power_instability":   4,
    "brownout":            4,
    "ekf_failure":         4,   # Raised: EKF failure precedes most crashes
    "pid_tuning_issue":    3,
    "rc_failsafe":         2,
    "crash_unknown":       1,
}

# Maps each failure label to the feature prefix carrying a ``_tanomaly``
# timestamp.  Kept at module level so it can be extended without touching
# the engine internals — new failure types only need to register here.
TANOMALY_PREFIX_MAP = {
    "vibration_high":      "vibe_z",
    "compass_interference": "mag",
    "power_instability":   "volt",
    "gps_quality_poor":    "gps_hdop",
    "motor_imbalance":     "motor_spread",
    "mechanical_failure":  "motor_spread",  # extreme motor differential → same onset source
    "ekf_failure":         "ekf_pos_var",
    "rc_failsafe":         "rc_failsafe",      # → rc_failsafe_tanomaly
    "pid_tuning_issue":    "pid_sat",           # → pid_sat_tanomaly
}

# Temporal arbiter tuning constants
TEMPORAL_TIE_WINDOW_US = 5_000_000    # 5 seconds — pure tie
TEMPORAL_PROXIMITY_US  = 30_000_000   # 30 seconds — "close enough to be downstream"
EXTREME_CONFIDENCE     = 0.85         # above this, the signal overrides proximity


class HybridEngine:
    """Combines RuleEngine + MLClassifier results.

    The pipeline is decomposed into three composable stages:

    1. ``_merge_signals`` — fuse rule + ML confidences into a single list.
    2. ``_temporal_arbiter`` — disambiguate root cause via earliest onset.
    3. ``_cascade_filter`` — prune low-quality secondary diagnoses.
    """

    def __init__(
        self,
        rule_engine: Optional[RuleEngine] = None,
        ml_classifier: Optional[MLClassifier] = None,
    ):
        self.rules = rule_engine or RuleEngine()
        self.ml = ml_classifier or MLClassifier()

    # ------------------------------------------------------------------
    # Stage 1: Merge rule + ML signals
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_signals(rule_results: list, ml_results: list) -> list:
        """Fuse rule-engine and ML-classifier outputs into ranked diagnoses."""
        rule_dict = {d["failure_type"]: d for d in rule_results}
        ml_dict = {d["failure_type"]: d for d in ml_results}

        all_types = set(rule_dict.keys()).union(set(ml_dict.keys()))

        merged: List[dict] = []

        for ftype in all_types:
            rule_conf = rule_dict[ftype]["confidence"] if ftype in rule_dict else 0.0
            ml_prob = ml_dict[ftype]["confidence"] if ftype in ml_dict else 0.0

            evidence: list = []
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
                # Rule-only: scale by 0.85 (not 0.75). A rule firing at 100% on a
                # 5x threshold breach (motor_spread=1005 vs limit=200) should not
                # be penalised to below the decision policy's abstain threshold.
                final = rule_conf * 0.85
                method = "rule"
            else:
                continue

            if final < MIN_MERGED_CONFIDENCE:
                continue

            severity = (
                "critical" if final > 0.6 else ("warning" if final > 0.3 else "info")
            )

            merged.append(
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

        merged.sort(key=rank, reverse=True)
        return merged

    # ------------------------------------------------------------------
    # Stage 2: Temporal Arbiter — disambiguate root cause by onset time
    # ------------------------------------------------------------------

    @staticmethod
    def _temporal_arbiter(
        merged_diagnoses: list,
        features: dict,
    ) -> Optional[list]:
        """Select the earliest-onset root cause when multiple candidates exist.

        Returns a single-element list if the arbiter fires, or ``None`` to
        let the cascade filter handle it instead.
        """
        if len(merged_diagnoses) < 2:
            return None

        # Build (tanomaly, confidence, diag) tuples for candidates with valid tanomaly
        timed_candidates = []
        for d in merged_diagnoses:
            ftype = d["failure_type"]
            prefix = TANOMALY_PREFIX_MAP.get(ftype)
            tanomaly = features.get(f"{prefix}_tanomaly", -1.0) if prefix else -1.0
            if tanomaly > 0:
                timed_candidates.append((tanomaly, d["confidence"], d))

        if not timed_candidates:
            return None

        # Sort by earliest onset, then by confidence for ties
        timed_candidates.sort(key=lambda x: (x[0], -x[1]))

        best_time, best_conf, best_diag = timed_candidates[0]
        root_cause = best_diag

        for t_time, t_conf, t_diag in timed_candidates[1:]:
            time_gap = t_time - best_time

            # Within pure tie window — prefer higher confidence
            if time_gap <= TEMPORAL_TIE_WINDOW_US and t_conf > best_conf:
                root_cause = t_diag
                best_conf = t_conf

            # Within proximity window AND this candidate has extreme confidence —
            # a 5× threshold breach appearing 10–30 seconds after an earlier signal
            # is likely the structural cause, not the downstream symptom.
            elif (
                time_gap <= TEMPORAL_PROXIMITY_US
                and t_conf >= EXTREME_CONFIDENCE
                and t_conf > best_conf + 0.15  # must be meaningfully higher
            ):
                root_cause = t_diag
                best_conf = t_conf

        root_cause = dict(root_cause)  # don't mutate original
        root_cause["recommendation"] = "[ARB] " + str(
            root_cause.get("recommendation", "")
        )
        return [root_cause]

    # ------------------------------------------------------------------
    # Stage 3: Cascade filter — prune low-quality secondary diagnoses
    # ------------------------------------------------------------------

    @staticmethod
    def _cascade_filter(merged_diagnoses: list) -> list:
        """Keep only the primary diagnosis plus strong secondaries.

        Critical rule-only diagnoses are never ejected — a rule that fires
        at full confidence on a massive threshold breach is trustworthy
        evidence even without ML corroboration.
        """
        if not merged_diagnoses:
            return []

        primary = merged_diagnoses[0]
        filtered = [primary]
        for d in merged_diagnoses[1:]:
            is_critical_rule = (
                d["detection_method"] == "rule"
                and d["severity"] == "critical"
            )
            if is_critical_rule:
                filtered.append(d)
            elif (
                d["confidence"] >= SECONDARY_MIN_CONFIDENCE
                and (primary["confidence"] - d["confidence"]) <= SECONDARY_MAX_GAP
            ):
                filtered.append(d)
            if len(filtered) >= MAX_HYBRID_DIAGNOSES:
                break
        return filtered

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def diagnose(self, features: dict) -> list:
        rule_results = self.rules.diagnose(features)
        ml_results = self.ml.predict(features) if self.ml.available else []
        self.last_explain_data = {"rule": rule_results, "ml": ml_results}

        merged = self._merge_signals(rule_results, ml_results)

        # Try temporal arbiter first; fall back to cascade filter
        arbiter_result = self._temporal_arbiter(merged, features)
        if arbiter_result is not None:
            return arbiter_result

        return self._cascade_filter(merged)
