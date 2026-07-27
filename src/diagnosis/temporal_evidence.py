"""Deterministic temporal-logic evidence over extracted anomaly onsets.

The rules use a small, auditable subset of metric temporal logic:

    cause -> F[min_delay,max_delay] effect

They do not create a diagnosis by themselves. They explain whether a proposed
upstream signal occurred before a known downstream symptom inside a physically
plausible causal window.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypedDict

from src.contracts import FeatureDict


TemporalStatus = Literal["satisfied", "violated", "not_evaluable"]


class TemporalEvidence(TypedDict):
    rule_id: str
    formula: str
    status: TemporalStatus
    cause_failure_type: str
    effect_failure_type: str
    cause_feature: str
    effect_feature: str
    cause_time_us: float | None
    effect_time_us: float | None
    delay_sec: float | None
    min_delay_sec: float
    max_delay_sec: float
    explanation: str


@dataclass(frozen=True)
class TemporalRule:
    rule_id: str
    cause_failure_type: str
    effect_failure_type: str
    cause_feature: str
    effect_feature: str
    min_delay_sec: float = 0.0
    max_delay_sec: float = 30.0

    @property
    def formula(self) -> str:
        return (
            f"{self.cause_feature} -> "
            f"F[{self.min_delay_sec:g},{self.max_delay_sec:g}] "
            f"{self.effect_feature}"
        )


DEFAULT_TEMPORAL_RULES = (
    TemporalRule(
        rule_id="vibration_precedes_ekf",
        cause_failure_type="vibration_high",
        effect_failure_type="ekf_failure",
        cause_feature="vibe_z_tanomaly",
        effect_feature="ekf_pos_var_tanomaly",
    ),
    TemporalRule(
        rule_id="compass_precedes_ekf",
        cause_failure_type="compass_interference",
        effect_failure_type="ekf_failure",
        cause_feature="mag_tanomaly",
        effect_feature="ekf_pos_var_tanomaly",
    ),
    TemporalRule(
        rule_id="gps_precedes_ekf",
        cause_failure_type="gps_quality_poor",
        effect_failure_type="ekf_failure",
        cause_feature="gps_hdop_tanomaly",
        effect_feature="ekf_pos_var_tanomaly",
    ),
    TemporalRule(
        rule_id="power_precedes_motor_stress",
        cause_failure_type="power_instability",
        effect_failure_type="motor_imbalance",
        cause_feature="volt_tanomaly",
        effect_feature="motor_spread_tanomaly",
    ),
    TemporalRule(
        rule_id="motor_fault_precedes_ekf",
        cause_failure_type="motor_imbalance",
        effect_failure_type="ekf_failure",
        cause_feature="motor_spread_tanomaly",
        effect_feature="ekf_pos_var_tanomaly",
    ),
)


def _onset_us(features: FeatureDict, feature_name: str) -> float | None:
    try:
        value = float(features.get(feature_name, -1.0))
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    return value


def evaluate_temporal_rule(
    features: FeatureDict,
    rule: TemporalRule,
) -> TemporalEvidence:
    cause_time = _onset_us(features, rule.cause_feature)
    effect_time = _onset_us(features, rule.effect_feature)
    if cause_time is None or effect_time is None:
        missing = []
        if cause_time is None:
            missing.append(rule.cause_feature)
        if effect_time is None:
            missing.append(rule.effect_feature)
        return {
            "rule_id": rule.rule_id,
            "formula": rule.formula,
            "status": "not_evaluable",
            "cause_failure_type": rule.cause_failure_type,
            "effect_failure_type": rule.effect_failure_type,
            "cause_feature": rule.cause_feature,
            "effect_feature": rule.effect_feature,
            "cause_time_us": cause_time,
            "effect_time_us": effect_time,
            "delay_sec": None,
            "min_delay_sec": rule.min_delay_sec,
            "max_delay_sec": rule.max_delay_sec,
            "explanation": (
                "Temporal rule not evaluable because onset data is missing for "
                + ", ".join(missing)
                + "."
            ),
        }

    delay_sec = (effect_time - cause_time) / 1e6
    satisfied = rule.min_delay_sec <= delay_sec <= rule.max_delay_sec
    if satisfied:
        explanation = (
            f"{rule.cause_failure_type} evidence preceded "
            f"{rule.effect_failure_type} evidence by {delay_sec:.2f}s, inside "
            f"the [{rule.min_delay_sec:g}, {rule.max_delay_sec:g}]s causal window."
        )
        status: TemporalStatus = "satisfied"
    else:
        explanation = (
            f"Observed delay {delay_sec:.2f}s is outside the "
            f"[{rule.min_delay_sec:g}, {rule.max_delay_sec:g}]s causal window; "
            "this rule does not support the proposed ordering."
        )
        status = "violated"

    return {
        "rule_id": rule.rule_id,
        "formula": rule.formula,
        "status": status,
        "cause_failure_type": rule.cause_failure_type,
        "effect_failure_type": rule.effect_failure_type,
        "cause_feature": rule.cause_feature,
        "effect_feature": rule.effect_feature,
        "cause_time_us": cause_time,
        "effect_time_us": effect_time,
        "delay_sec": delay_sec,
        "min_delay_sec": rule.min_delay_sec,
        "max_delay_sec": rule.max_delay_sec,
        "explanation": explanation,
    }


def evaluate_temporal_evidence(
    features: FeatureDict,
    rules: tuple[TemporalRule, ...] = DEFAULT_TEMPORAL_RULES,
    *,
    include_not_evaluable: bool = False,
) -> list[TemporalEvidence]:
    """Evaluate all temporal rules in deterministic declaration order."""

    evidence = [evaluate_temporal_rule(features, rule) for rule in rules]
    if include_not_evaluable:
        return evidence
    return [
        item
        for item in evidence
        if item["status"] != "not_evaluable"
    ]
