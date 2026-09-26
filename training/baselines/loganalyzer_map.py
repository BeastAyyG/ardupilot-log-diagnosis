"""Map ArduPilot LogAnalyzer checks to our diagnosis label set.

LogAnalyzer (the historical ``Tools/LogAnalyzer`` script in the ArduPilot repo)
performs a fixed set of per-channel sanity checks and emits a verdict per check
such as ``Vibe levels high``, ``Compass offsets``, ``GPS Glitch``, ``Brownout``,
``Thrust Loss``, ``RC failsafe``, ``Motor balance``, ``Power``, ``EKF``,
``PID``, ``Autotune``. That tool's old path is gone (see plan Step 4), so this
module is a **static, documented translation** of those known checks into the
labels used by this benchmark. It does not re-run LogAnalyzer; the maintainer
runs LogAnalyzer elsewhere and passes its per-check verdicts in as a dict.

Verdict input shape (what the maintainer builds from LogAnalyzer output)::

    {"Vibe levels": "high", "Compass": "review", "GPS": "glitch", ...}

Mapping is conservative: a check only maps to a label when its verdict is the
failure-leaning one. Anything unknown returns no label (abstention), which the
evaluation counts as "no diagnosis" rather than a wrong one.

Verified against ``VALID_LABELS`` in ``src/constants.py``; every target here is a
real label.
"""

from __future__ import annotations

import re

# LogAnalyzer check-name (case-insensitive) -> {verdict-substring: label}
# Only the failure-leaning verdict maps; neutral/ok verdicts abstain.
CHECK_MAP: dict[str, dict[str, str]] = {
    "vibe": {"high": "vibration_high"},
    "vibration": {"high": "vibration_high"},
    "compass": {"offsets": "compass_interference", "review": "compass_interference", "bad": "compass_interference"},
    "mag": {"offsets": "compass_interference"},
    "gps": {"glitch": "gps_quality_poor", "bad": "gps_quality_poor", "errors": "gps_quality_poor"},
    "ekf": {"bad": "ekf_failure", "unhealthy": "ekf_failure"},
    "thrust": {"loss": "thrust_loss"},
    "motor": {"balance": "motor_imbalance", "imbalance": "motor_imbalance"},
    "rc": {"failsafe": "rc_failsafe", "fs": "rc_failsafe"},
    "power": {"brownout": "brownout", "low": "power_instability"},
    "brownout": {"detected": "brownout", "yes": "brownout"},
    "pid": {"bad": "pid_tuning_issue", "oscillation": "pid_tuning_issue"},
    "autotune": {"bad": "pid_tuning_issue"},
    "mechanical": {"failure": "mechanical_failure"},
}

# Labels LogAnalyzer simply cannot produce (config / link-layer / unknown). The
# evaluation must still report them as "not covered by this baseline".
UNMAPPED_LABELS = {
    "setup_error",
    "crash_unknown",
    "healthy",
}


def predict_label(report: dict) -> str | None:
    """Return the single best LogAnalyzer-derived label, or ``None``.

    ``report`` is expected to carry a ``loganalyzer`` key: a dict of
    check-name -> verdict string. If absent, abstain.
    """
    verdicts = report.get("loganalyzer")
    if not isinstance(verdicts, dict):
        return None
    hits: list[str] = []
    for check, verdict in verdicts.items():
        key = (check or "").strip().lower()
        if verdict is None:
            continue
        verdict_text = str(verdict).strip().lower()
        for check_prefix, mapping in CHECK_MAP.items():
            if not key.startswith(check_prefix):
                continue
            for sub, label in mapping.items():
                if sub in re.sub(r"[^a-z ]", " ", verdict_text):
                    hits.append(label)
            break
    if not hits:
        return None
    # Deterministic choice: first hit by label order, so the result is stable.
    for label in sorted(set(hits)):
        return label
    return None  # unreachable, but keeps the type clear


def coverage() -> dict[str, list[str]]:
    """Which labels this baseline can and cannot produce (for the paper)."""
    can = sorted({label for mapping in CHECK_MAP.values() for label in mapping.values()})
    return {"can_predict": can, "cannot_predict": sorted(UNMAPPED_LABELS)}
