"""Safety-first decision policy for diagnosis outputs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
from typing import Any, cast

from src.contracts import (
    CapabilityStatus,
    DecisionDict,
    DecisionStatus,
    DiagnosisDict,
    RankedSubsystem,
)


SELECTION_POLICY_VERSION = "selective-v2"

DIAGNOSIS_CAPABILITY_MAP = {
    "vibration_high": "vibration_analysis",
    "compass_interference": "compass_gps_navigation",
    "gps_quality_poor": "compass_gps_navigation",
    "power_instability": "power_battery_dynamics",
    "brownout": "power_battery_dynamics",
    "ekf_failure": "ekf_state_estimation",
    "motor_imbalance": "motor_balance_mechanics",
    "mechanical_failure": "motor_balance_mechanics",
    "thrust_loss": "motor_balance_mechanics",
    "setup_error": "motor_balance_mechanics",
    "pid_tuning_issue": "pid_rate_control",
    "rc_failsafe": "event_failsafe_tracking",
    "crash_unknown": "event_failsafe_tracking",
}

SUBSYSTEM_MAP = {
    "vibration_high": "Vibration/Mounts",
    "compass_interference": "Magnetics/EMI",
    "power_instability": "Power/Battery",
    "brownout": "Power/Battery",
    "gps_quality_poor": "GPS/Antenna",
    "motor_imbalance": "Propulsion/Motors",
    "thrust_loss": "Propulsion/Thrust",
    "setup_error": "Vehicle/Setup",
    "pid_tuning_issue": "Control/PID",
    "mechanical_failure": "Hardware/Frame",
    "ekf_failure": "Navigation/EKF",
    "rc_failsafe": "Radio/Receiver",
    "crash_unknown": "Unknown",
}


def _safe_confidence(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def _quality_context(
    top_guess: str | None,
    metadata: Mapping[str, Any] | None,
    quality_report: Mapping[str, Any] | None,
    extraction_success: bool | None,
) -> tuple[str | None, CapabilityStatus, str, bool | None]:
    if metadata:
        if quality_report is None:
            candidate = metadata.get("quality_report")
            if isinstance(candidate, Mapping):
                quality_report = candidate
        if extraction_success is None:
            value = metadata.get("extraction_success")
            if isinstance(value, bool):
                extraction_success = value

    overall_status = "UNKNOWN"
    capability_name = DIAGNOSIS_CAPABILITY_MAP.get(top_guess or "")
    capability_status: CapabilityStatus = "UNKNOWN"
    if quality_report:
        overall_status = str(quality_report.get("overall_status", "UNKNOWN")).upper()
        capabilities = quality_report.get("capabilities", {})
        if capability_name and isinstance(capabilities, Mapping):
            capability = capabilities.get(capability_name)
            if isinstance(capability, Mapping):
                raw_status = str(capability.get("status", "UNKNOWN")).upper()
                if raw_status in {"RELIABLE", "DEGRADED", "UNSUPPORTED"}:
                    capability_status = cast(CapabilityStatus, raw_status)

    return capability_name, capability_status, overall_status, extraction_success


def _rank_subsystems(diagnoses: Sequence[DiagnosisDict]) -> list[RankedSubsystem]:
    subsystem_scores: dict[str, float] = {}
    for diagnosis in diagnoses:
        failure_type = diagnosis.get("failure_type", "crash_unknown")
        subsystem = SUBSYSTEM_MAP.get(failure_type, "Unknown")
        confidence = _safe_confidence(diagnosis.get("confidence", 0.0))
        if not math.isfinite(confidence):
            confidence = 0.0
        subsystem_scores[subsystem] = max(
            confidence,
            subsystem_scores.get(subsystem, 0.0),
        )

    ranked = sorted(
        [
            {"subsystem": subsystem, "likelihood": likelihood}
            for subsystem, likelihood in subsystem_scores.items()
        ],
        key=lambda item: item["likelihood"],
        reverse=True,
    )
    return cast(list[RankedSubsystem], ranked)


def _decision(
    *,
    status: DecisionStatus,
    requires_human_review: bool,
    top_guess: str | None,
    top_confidence: float,
    rationale: list[str],
    abstention_reasons: list[str],
    diagnoses: Sequence[DiagnosisDict],
    applicable_capability: str | None,
    capability_status: CapabilityStatus,
) -> DecisionDict:
    return {
        "status": status,
        "requires_human_review": requires_human_review,
        "top_guess": top_guess,
        "top_confidence": top_confidence,
        "rationale": rationale,
        "abstention_reasons": abstention_reasons,
        "ranked_subsystems": _rank_subsystems(diagnoses),
        "applicable_capability": applicable_capability,
        "capability_status": capability_status,
        "selection_policy": SELECTION_POLICY_VERSION,
    }


def evaluate_decision(
    diagnoses: Sequence[DiagnosisDict],
    abstain_threshold: float = 0.65,
    close_margin: float = 0.15,
    *,
    metadata: Mapping[str, Any] | None = None,
    quality_report: Mapping[str, Any] | None = None,
    extraction_success: bool | None = None,
    ml_confirmation_allowed: bool | None = None,
    ml_risk_reason: str | None = None,
) -> DecisionDict:
    top_guess = (
        str(diagnoses[0].get("failure_type", "unknown"))
        if diagnoses
        else None
    )
    capability_name, capability_status, overall_status, extraction_success = (
        _quality_context(
            top_guess,
            metadata,
            quality_report,
            extraction_success,
        )
    )

    if not diagnoses:
        if extraction_success is False:
            return _decision(
                status="insufficient_data",
                requires_human_review=True,
                top_guess=None,
                top_confidence=0.0,
                rationale=[
                    "Feature extraction did not produce enough telemetry for diagnosis."
                ],
                abstention_reasons=["extraction_failed"],
                diagnoses=diagnoses,
                applicable_capability=None,
                capability_status="UNSUPPORTED",
            )
        if overall_status == "UNSUPPORTED":
            return _decision(
                status="insufficient_data",
                requires_human_review=True,
                top_guess=None,
                top_confidence=0.0,
                rationale=[
                    "Log quality is unsupported; absence of a finding cannot clear the vehicle."
                ],
                abstention_reasons=["log_quality_unsupported"],
                diagnoses=diagnoses,
                applicable_capability=None,
                capability_status="UNSUPPORTED",
            )
        if overall_status == "DEGRADED":
            return _decision(
                status="uncertain",
                requires_human_review=True,
                top_guess=None,
                top_confidence=0.0,
                rationale=[
                    "No fault crossed the detection threshold, but some diagnostic "
                    "capabilities are degraded or unavailable."
                ],
                abstention_reasons=["log_quality_degraded"],
                diagnoses=diagnoses,
                applicable_capability=None,
                capability_status="DEGRADED",
            )
        return _decision(
            status="no_fault_detected",
            requires_human_review=False,
            top_guess=None,
            top_confidence=0.0,
            rationale=[
                "No supported fault detector crossed its reporting threshold. "
                "This is not a safe-to-fly certification."
            ],
            abstention_reasons=[],
            diagnoses=diagnoses,
            applicable_capability=None,
            capability_status=(
                "RELIABLE" if overall_status == "RELIABLE" else "UNKNOWN"
            ),
        )

    top = diagnoses[0]
    top_conf = _safe_confidence(top.get("confidence", 0.0))
    rationale: list[str] = []
    abstention_reasons: list[str] = []

    # Non-finite confidence is never evidence for a confirmed finding. Check
    # every candidate, not only the top-ranked one, so NaN/Inf cannot hide in a
    # competing diagnosis and bypass the ambiguity gate.
    nonfinite_confidences = False
    for diagnosis in diagnoses:
        candidate_confidence = _safe_confidence(diagnosis.get("confidence", 0.0))
        if not math.isfinite(candidate_confidence):
            nonfinite_confidences = True
            break
    if nonfinite_confidences:
        if not math.isfinite(top_conf):
            top_conf = 0.0
        rationale.append("A diagnosis confidence is non-finite; evidence is rejected.")
        abstention_reasons.append("nonfinite_confidence")

    if capability_status == "UNSUPPORTED":
        return _decision(
            status="insufficient_data",
            requires_human_review=True,
            top_guess=top_guess,
            top_confidence=top_conf,
            rationale=[
                f"{capability_name} is unsupported by the available telemetry; "
                f"{top_guess} is retained only as an unverified hypothesis."
            ],
            abstention_reasons=["required_capability_unsupported"],
            diagnoses=diagnoses,
            applicable_capability=capability_name,
            capability_status=capability_status,
        )

    uncertain = nonfinite_confidences
    if capability_status == "DEGRADED":
        uncertain = True
        rationale.append(
            f"{capability_name} is degraded; the candidate cannot be confirmed."
        )
        abstention_reasons.append("required_capability_degraded")

    if top_conf < abstain_threshold:
        uncertain = True
        rationale.append(
            f"Top confidence below abstain threshold ({top_conf:.2f} < {abstain_threshold:.2f})."
        )
        abstention_reasons.append("confidence_below_threshold")

    if len(diagnoses) > 1:
        strongest_alternative = max(
            diagnoses[1:],
            key=lambda item: _safe_confidence(item.get("confidence", 0.0)),
        )
        second_conf = _safe_confidence(
            strongest_alternative.get("confidence", 0.0)
        )
        if not math.isfinite(second_conf):
            second_conf = 0.0
        confidence_gap = abs(top_conf - second_conf)
        if second_conf > top_conf:
            uncertain = True
            rationale.append(
                "Causal root-cause confidence is lower than the strongest "
                f"competing finding ({top_conf:.2f} < {second_conf:.2f})."
            )
            abstention_reasons.append("stronger_competing_finding")
        if confidence_gap < close_margin:
            uncertain = True
            rationale.append(
                "Top-2 confidence separation is small "
                f"(|{top_conf:.2f} - {second_conf:.2f}| < {close_margin:.2f})."
            )
            abstention_reasons.append("top2_margin_too_small")

    high_conf_count = sum(
        1
        for d in diagnoses
        if math.isfinite(_safe_confidence(d.get("confidence", 0.0)))
        and _safe_confidence(d.get("confidence", 0.0)) >= 0.5
    )
    if high_conf_count > 1:
        uncertain = True
        rationale.append(
            "Multiple high-confidence diagnoses detected; likely cascading symptoms."
        )
        abstention_reasons.append("multiple_high_confidence_findings")

    if top.get("detection_method") == "ml" and top_conf < 0.75:
        uncertain = True
        rationale.append("Top diagnosis is ML-only with moderate confidence.")
        abstention_reasons.append("moderate_ml_only_finding")

    if (
        top.get("detection_method") == "ml"
        and ml_confirmation_allowed is not True
    ):
        uncertain = True
        rationale.append(
            ml_risk_reason
            or (
                "ML confirmation is disabled because the saved calibration and "
                "false-critical risk gates have not both passed."
            )
        )
        abstention_reasons.append("ml_risk_control_not_passed")

    if uncertain:
        status: DecisionStatus = "uncertain"
        requires_review = True
    else:
        status = "confirmed"
        requires_review = False
        rationale.append("Top diagnosis confidence and separation pass safety gate.")

    return _decision(
        status=status,
        requires_human_review=requires_review,
        top_guess=top_guess,
        top_confidence=top_conf,
        rationale=rationale,
        abstention_reasons=abstention_reasons,
        diagnoses=diagnoses,
        applicable_capability=capability_name,
        capability_status=capability_status,
    )
