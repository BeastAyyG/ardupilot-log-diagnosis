from src.diagnosis.causal_graph import (
    CausalEdge,
    evaluate_causal_edge,
    evaluate_causal_graph,
)


def test_graph_edge_requires_both_onsets_and_is_auditable():
    edge = CausalEdge("x", "power_instability", "motor_imbalance", "cause", "effect", max_delay_sec=5, required_evidence=("cause", "effect"))
    result = evaluate_causal_edge({"cause": 1_000_000}, edge)
    assert result["status"] == "not_evaluable"
    assert result["required_evidence"] == ["cause", "effect"]
    assert result["graph_version"] == "1.0"


def test_graph_edge_rejects_late_or_reverse_effect():
    edge = CausalEdge("x", "vibration_high", "ekf_failure", "cause", "effect", max_delay_sec=5, required_evidence=("cause", "effect"))
    result = evaluate_causal_edge({"cause": 10_000_000, "effect": 20_000_001}, edge)
    assert result["status"] == "violated"
    assert result["delay_sec"] > 5


def test_graph_only_reports_evidence_and_does_not_diagnose():
    results = evaluate_causal_graph({"vibe_z_tanomaly": 100_000_000, "ekf_pos_var_tanomaly": 104_000_000})
    vibration = next(item for item in results if item["edge_id"] == "vibration_to_ekf_variance")
    assert vibration["status"] == "satisfied"
    assert all("diagnosis" not in item for item in results)
