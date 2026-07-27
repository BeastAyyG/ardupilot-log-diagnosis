from src.diagnosis.hybrid_engine import HybridEngine
from src.diagnosis.temporal_evidence import (
    TemporalRule,
    evaluate_temporal_evidence,
    evaluate_temporal_rule,
)


def test_temporal_rule_is_satisfied_inside_causal_window():
    rule = TemporalRule(
        rule_id="cause_then_effect",
        cause_failure_type="power_instability",
        effect_failure_type="motor_imbalance",
        cause_feature="cause_onset",
        effect_feature="effect_onset",
        max_delay_sec=10.0,
    )

    evidence = evaluate_temporal_rule(
        {
            "cause_onset": 100_000_000,
            "effect_onset": 106_500_000,
        },
        rule,
    )

    assert evidence["status"] == "satisfied"
    assert evidence["delay_sec"] == 6.5
    assert evidence["formula"] == "cause_onset -> F[0,10] effect_onset"


def test_temporal_rule_rejects_reverse_ordering():
    rule = TemporalRule(
        rule_id="cause_then_effect",
        cause_failure_type="vibration_high",
        effect_failure_type="ekf_failure",
        cause_feature="cause_onset",
        effect_feature="effect_onset",
    )

    evidence = evaluate_temporal_rule(
        {
            "cause_onset": 110_000_000,
            "effect_onset": 100_000_000,
        },
        rule,
    )

    assert evidence["status"] == "violated"
    assert evidence["delay_sec"] == -10.0


def test_missing_onset_is_not_evaluable_and_hidden_by_default():
    rule = TemporalRule(
        rule_id="missing_effect",
        cause_failure_type="gps_quality_poor",
        effect_failure_type="ekf_failure",
        cause_feature="gps_onset",
        effect_feature="ekf_onset",
    )
    features = {"gps_onset": 100_000_000}

    evidence = evaluate_temporal_rule(features, rule)

    assert evidence["status"] == "not_evaluable"
    assert evaluate_temporal_evidence(features, (rule,)) == []
    assert len(
        evaluate_temporal_evidence(
            features,
            (rule,),
            include_not_evaluable=True,
        )
    ) == 1


class _NoDiagnosisRules:
    def diagnose(self, _features):
        return []


class _NoML:
    available = False


class _NoAnomaly:
    available = False


def test_hybrid_explain_data_includes_temporal_evidence():
    engine = HybridEngine(
        rule_engine=_NoDiagnosisRules(),
        ml_classifier=_NoML(),
        anomaly_detector=_NoAnomaly(),
    )

    engine.diagnose(
        {
            "vibe_z_tanomaly": 100_000_000,
            "ekf_pos_var_tanomaly": 104_000_000,
        }
    )

    temporal = engine.last_explain_data["temporal_evidence"]
    assert temporal[0]["rule_id"] == "vibration_precedes_ekf"
    assert temporal[0]["status"] == "satisfied"
