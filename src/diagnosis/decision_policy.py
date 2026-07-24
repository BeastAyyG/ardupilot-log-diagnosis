"""Safety-first decision policy for diagnosis outputs."""

from __future__ import annotations

from typing import List, cast

from src.contracts import DecisionDict, DiagnosisDict, RankedSubsystem


def evaluate_decision(
    diagnoses: List[DiagnosisDict],
    abstain_threshold: float = 0.65,
    close_margin: float = 0.15,
) -> DecisionDict:
    if not diagnoses:
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

    uncertain = False
    if top_conf < abstain_threshold:
        uncertain = True
        rationale.append(
            f"Top confidence below abstain threshold ({top_conf:.2f} < {abstain_threshold:.2f})."
        )

    if len(diagnoses) > 1:
        strongest_alternative = max(
            diagnoses[1:],
            key=lambda item: float(item.get("confidence", 0.0)),
        )
        second_conf = float(strongest_alternative.get("confidence", 0.0))
        confidence_gap = abs(top_conf - second_conf)
        if second_conf > top_conf:
            uncertain = True
            rationale.append(
                "Causal root-cause confidence is lower than the strongest "
                f"competing finding ({top_conf:.2f} < {second_conf:.2f})."
            )
        if confidence_gap < close_margin:
            uncertain = True
            rationale.append(
                "Top-2 confidence separation is small "
                f"(|{top_conf:.2f} - {second_conf:.2f}| < {close_margin:.2f})."
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
