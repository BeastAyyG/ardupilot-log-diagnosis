"""Versioned, fail-closed causal graph evidence.

The graph is deliberately descriptive: evaluating an edge produces evidence
for ``explain_data`` but never selects or creates a diagnosis.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypedDict

from src.contracts import FeatureDict

CausalStatus = Literal["satisfied", "violated", "not_evaluable"]
CAUSAL_GRAPH_VERSION = "1.0"


class CausalEvidence(TypedDict):
    graph_version: str
    edge_id: str
    cause_failure_type: str
    effect_failure_type: str
    cause_feature: str
    effect_feature: str
    required_evidence: list[str]
    confounders: list[str]
    contradictions: list[str]
    cause_time_us: float | None
    effect_time_us: float | None
    delay_sec: float | None
    max_delay_sec: float
    status: CausalStatus
    explanation: str


@dataclass(frozen=True)
class CausalEdge:
    edge_id: str
    cause_failure_type: str
    effect_failure_type: str
    cause_feature: str
    effect_feature: str
    max_delay_sec: float = 30.0
    required_evidence: tuple[str, ...] = ()
    confounders: tuple[str, ...] = ()
    contradictions: tuple[str, ...] = ()

    @property
    def formula(self) -> str:
        return f"{self.cause_feature} -> F[0,{self.max_delay_sec:g}] {self.effect_feature}"


DEFAULT_CAUSAL_GRAPH = (
    CausalEdge("power_sag_to_motor_stress", "power_instability", "motor_imbalance", "volt_tanomaly", "motor_spread_tanomaly", required_evidence=("volt_tanomaly", "motor_spread_tanomaly")),
    # Controller-reset telemetry is firmware/message dependent; the edge is
    # therefore normally ``not_evaluable`` unless an extractor supplies it.
    CausalEdge("power_sag_to_controller_reset", "power_instability", "controller_reset", "volt_tanomaly", "controller_reset_tanomaly", max_delay_sec=10.0, required_evidence=("volt_tanomaly", "controller_reset_tanomaly")),
    CausalEdge("motor_imbalance_to_vibration", "motor_imbalance", "vibration_high", "motor_spread_tanomaly", "vibe_z_tanomaly", required_evidence=("motor_spread_tanomaly", "vibe_z_tanomaly")),
    CausalEdge("vibration_to_ekf_variance", "vibration_high", "ekf_failure", "vibe_z_tanomaly", "ekf_pos_var_tanomaly", max_delay_sec=30.0, required_evidence=("vibe_z_tanomaly", "ekf_pos_var_tanomaly")),
    CausalEdge("compass_to_ekf_variance", "compass_interference", "ekf_failure", "mag_tanomaly", "ekf_pos_var_tanomaly", required_evidence=("mag_tanomaly", "ekf_pos_var_tanomaly")),
    CausalEdge("gps_to_ekf_variance", "gps_quality_poor", "ekf_failure", "gps_hdop_tanomaly", "ekf_pos_var_tanomaly", required_evidence=("gps_hdop_tanomaly", "ekf_pos_var_tanomaly")),
)


def _onset(features: FeatureDict, name: str) -> float | None:
    try:
        value = float(features.get(name, -1.0))
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def evaluate_causal_edge(features: FeatureDict, edge: CausalEdge) -> CausalEvidence:
    cause_time, effect_time = _onset(features, edge.cause_feature), _onset(features, edge.effect_feature)
    missing = [name for name in edge.required_evidence if _onset(features, name) is None]
    confounders = [name for name in edge.confounders if _onset(features, name) is not None or bool(features.get(name))]
    contradictions = [name for name in edge.contradictions if _onset(features, name) is not None or bool(features.get(name))]
    base = dict(graph_version=CAUSAL_GRAPH_VERSION, edge_id=edge.edge_id, cause_failure_type=edge.cause_failure_type, effect_failure_type=edge.effect_failure_type, cause_feature=edge.cause_feature, effect_feature=edge.effect_feature, required_evidence=list(edge.required_evidence), confounders=confounders, contradictions=contradictions, cause_time_us=cause_time, effect_time_us=effect_time, delay_sec=None, max_delay_sec=edge.max_delay_sec)
    if missing:
        base.update(status="not_evaluable", explanation="Required evidence missing: " + ", ".join(missing) + ".")
        return base  # type: ignore[return-value]
    delay = (effect_time - cause_time) / 1e6
    base["delay_sec"] = delay
    if confounders or contradictions or delay < 0 or delay > edge.max_delay_sec:
        reasons = []
        if delay < 0 or delay > edge.max_delay_sec:
            reasons.append(f"delay {delay:.2f}s outside [0,{edge.max_delay_sec:g}]s")
        if confounders:
            reasons.append("confounders present: " + ", ".join(confounders))
        if contradictions:
            reasons.append("contradictions present: " + ", ".join(contradictions))
        base.update(status="violated", explanation="; ".join(reasons) + ".")
    else:
        base.update(status="satisfied", explanation=f"{edge.cause_failure_type} preceded {edge.effect_failure_type} by {delay:.2f}s inside the causal window.")
    return base  # type: ignore[return-value]


def evaluate_causal_graph(features: FeatureDict, edges: tuple[CausalEdge, ...] = DEFAULT_CAUSAL_GRAPH, *, include_not_evaluable: bool = True) -> list[CausalEvidence]:
    """Evaluate declared edges in deterministic order; no diagnosis is inferred."""
    result = [evaluate_causal_edge(features, edge) for edge in edges]
    return result if include_not_evaluable else [item for item in result if item["status"] != "not_evaluable"]
