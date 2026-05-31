"""Parameter-drift rule check.

Runs in-flight parameter-drift detection against the raw PARM stream stashed in
``features`` under ``_raw_parm_messages`` (injected by the feature pipeline),
using the thresholds the active ``RuleEngine`` was configured with. Detection is
performed here — not at feature-extraction time — so custom threshold overrides
(e.g. from a YAML config) are honoured.

The rule lives inside the ``RuleEngine`` so it appears in the explain / rule
panels, but ``parameter_drift`` is an advisory label (see ``ADVISORY_LABELS``)
and is routed out of the scored crash-diagnosis list by the engine.
"""

from __future__ import annotations

from src.contracts import DiagnosisDict, EvidenceItem, FeatureDict
from src.diagnosis.failure_types import FAILURE_RECOMMENDATIONS
from src.diagnosis.parameter_drift import detect_drift_from_features

# Cap so a noisy log can't produce hundreds of evidence rows.
_MAX_EVIDENCE = 8


def check_parameter_drift(features: FeatureDict, thresholds: dict) -> DiagnosisDict | None:
    events = detect_drift_from_features(features, thresholds)
    if not events:
        return None

    count = len({event.get("parameter") for event in events})
    if count <= 0:
        return None

    any_tuning_critical = any(bool(event.get("tuning_critical")) for event in events)

    # Confidence grows modestly with the number of distinct parameters changed
    # and is capped so this advisory never out-ranks a real crash signature.
    base = 0.30 + 0.10 * count
    if any_tuning_critical:
        base += 0.15
    confidence = min(base, 0.60)

    evidence: list[EvidenceItem] = []
    for event in events[:_MAX_EVIDENCE]:
        evidence.append(
            {
                "feature": str(event.get("parameter", "?")),
                "value": f"{event.get('old_value')} -> {event.get('new_value')}",
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
