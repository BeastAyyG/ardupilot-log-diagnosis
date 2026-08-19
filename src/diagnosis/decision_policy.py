"""Safety-first decision policy for diagnosis outputs."""

from __future__ import annotations

from typing import List, cast

from src.contracts import DecisionDict, DiagnosisDict, RankedSubsystem
from src.parser.capabilities import capability_supports_format


def evaluate_decision(
    diagnoses: List[DiagnosisDict],
    abstain_threshold: float = 0.65,
    close_margin: float = 0.15,
    quality_report: dict | None = None,
) -> DecisionDict:
    """Apply the safety gate to diagnoses and input quality.

    An empty diagnosis is only a healthy result when the input was actually
    usable.  Parsers can return a structurally valid object after a truncated,
    unsupported, or otherwise incomplete log; treating that object as a clean
    flight silently converts missing evidence into a false negative.  Callers
    that have a quality report should pass it here so degraded input becomes an
    explicit review/abstention outcome.
    """
    quality_status = ""
    format_requires_review = False
    format_name = None
    if isinstance(quality_report, dict):
        quality_status = str(quality_report.get("overall_status", "")).strip().lower()
        format_info = quality_report.get("input_format")
        if isinstance(format_info, dict):
            format_name = format_info.get("format")
        elif format_info:
            format_name = format_info
        format_requires_review = bool(
            format_name and not capability_supports_format("diagnosis", format_name)
        )
    quality_requires_review = quality_status in {
        "unsupported",
        "insufficient_data",
        "insufficient",
        "unusable",
        "invalid",
        "truncated",
        "partial",
        "degraded",
        "unknown",
    }
    quality_requires_review = quality_requires_review or format_requires_review

    if not diagnoses:
        if quality_requires_review:
            format_note = (
                f"ArduPilot root-cause diagnosis is not declared for input format '{format_name}'."
                if format_requires_review
                else None
            )
            return {
                "status": "uncertain",
                "requires_human_review": True,
                "top_guess": None,
                "top_confidence": 0.0,
                "rationale": [
                    *([format_note] if format_note else []),
                    f"Input quality is {quality_status.upper() or 'UNKNOWN'}; an empty diagnosis cannot be treated as healthy.",
                    "Review the log-quality report and obtain the missing or intact telemetry before clearing the flight.",
                ],
                "ranked_subsystems": [],
            }
        return {
            "status": "healthy",
            "requires_human_review": False,
            "top_guess": None,
            "top_confidence": 0.0,
            "rationale": ["No critical diagnosis produced."],
            "ranked_subsystems": [],
        }

    top = diagnoses[0]
    top_conf = float(top.get("confidence", 0.0))
    top_guess = str(top.get("failure_type", "unknown"))
    rationale = []

    uncertain = quality_requires_review
    if format_requires_review:
        rationale.append(
            f"ArduPilot root-cause diagnosis is not declared for input format '{format_name}'; finding is not actionable without a supported DataFlash log."
        )
    if quality_requires_review:
        rationale.append(
            f"Input quality is {quality_status.upper() or 'UNKNOWN'}; diagnosis is provisional and requires human review."
        )
    if top_conf < abstain_threshold:
        uncertain = True
        rationale.append(
            f"Top confidence below abstain threshold ({top_conf:.2f} < {abstain_threshold:.2f})."
        )

    if len(diagnoses) > 1:
        second_conf = float(diagnoses[1].get("confidence", 0.0))
        if (top_conf - second_conf) < close_margin:
            uncertain = True
            rationale.append(
                f"Top-2 confidence gap is small ({top_conf:.2f} - {second_conf:.2f} < {close_margin:.2f})."
            )

    high_conf_count = sum(
        1 for d in diagnoses if float(d.get("confidence", 0.0)) >= 0.5
    )
    if high_conf_count > 1:
        uncertain = True
        rationale.append(
            "Multiple high-confidence diagnoses detected; likely cascading symptoms."
        )

    if top.get("detection_method") == "ml" and top_conf < 0.75:
        uncertain = True
        rationale.append("Top diagnosis is ML-only with moderate confidence.")

    if uncertain:
        status = "uncertain"
        requires_review = True
    else:
        status = "confirmed"
        requires_review = False
        rationale.append("Top diagnosis confidence and separation pass safety gate.")

    SUBSYSTEM_MAP = {
        "vibration_high": "Vibration/Mounts",
        "compass_interference": "Magnetics/EMI",
        "power_instability": "Power/Battery",
        "brownout": "Power/Battery",
        "gps_quality_poor": "GPS/Antenna",
        "motor_imbalance": "Propulsion/Motors",
        "thrust_loss": "Propulsion/Thrust",
        "pid_tuning_issue": "Control/PID",
        "mechanical_failure": "Hardware/Frame",
        "ekf_failure": "Navigation/EKF",
        "rc_failsafe": "Radio/Receiver",
        "crash_unknown": "Unknown",
    }

    subsystem_scores = {}
    for d in diagnoses:
        ftype = d.get("failure_type", "crash_unknown")
        sub_name = SUBSYSTEM_MAP.get(ftype, "Unknown")
        conf = float(d.get("confidence", 0.0))
        # Keep track of the highest confidence per subsystem
        if conf > subsystem_scores.get(sub_name, 0.0):
            subsystem_scores[sub_name] = conf

    ranked_subsystems = sorted(
        [{"subsystem": k, "likelihood": v} for k, v in subsystem_scores.items()],
        key=lambda x: x["likelihood"],
        reverse=True,
    )

    return {
        "status": status,
        "requires_human_review": requires_review,
        "top_guess": top_guess,
        "top_confidence": top_conf,
        "rationale": rationale,
        "ranked_subsystems": cast(list[RankedSubsystem], ranked_subsystems),
    }
