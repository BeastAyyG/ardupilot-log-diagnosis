"""Parameter-drift rule check.

Reads the private ``_param_drift_*`` signals injected by the feature pipeline
(populated from the ``PARM`` timeline by ``src.diagnosis.parameter_drift``) and
emits a ``parameter_drift`` advisory diagnosis. The rule lives inside the
``RuleEngine`` so it shows up in the explain / rule-output panels, but
``parameter_drift`` is an advisory label (see ``ADVISORY_LABELS``) and is routed
out of the scored crash-diagnosis list by the engine.
"""

from __future__ import annotations

from typing import Any

from src.contracts import DiagnosisDict, FeatureDict, EvidenceItem
from src.diagnosis.failure_types import FAILURE_RECOMMENDATIONS

# Cap so a noisy log can't produce hundreds of evidence rows.
_MAX_EVIDENCE = 8


def check_parameter_drift(features: FeatureDict, thresholds: dict) -> DiagnosisDict | None:
    events = features.get("_param_drift_events") or []
    if not events:
        return None

    try:
        count = int(float(features.get("_param_drift_count", 0.0) or 0.0))
    except (TypeError, ValueError):
        count = len({e.get("parameter") for e in events})
    if count <= 0:
        return None

    any_tuning_critical = any(bool(e.get("tuning_critical")) for e in events)

    # Confidence grows modestly with the number of distinct parameters changed
    # and is capped so this advisory never out-ranks a real crash signature.
    base = 0.30 + 0.10 * count
    if any_tuning_critical:
        base += 0.15
    confidence = min(base, 0.60)

    evidence: list[EvidenceItem] = []
    for event in events[:_MAX_EVIDENCE]:
        old_v = event.get("old_value")
        new_v = event.get("new_value")
        evidence.append(
            {
                "feature": str(event.get("parameter", "?")),
                "value": f"{old_v} -> {new_v}",
                "threshold": "in-flight change",
                "direction": "changed",
            }
        )

    severity = "warning" if any_tuning_critical else "info"
    return {
        "failure_type": "parameter_drift",
        "confidence": float(confidence),
        "severity": severity,
        "detection_method": "rule",
        "evidence": evidence,
        "recommendation": FAILURE_RECOMMENDATIONS["parameter_drift"],
        "reason_code": "advisory",
    }