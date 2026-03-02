"""Hard-Gate verification tests (Gates A–E).

Gate A: 0 diagnosis runtime crashes on any valid/malformed input.
Gate B: 100% of predictions include evidence + recommendation.
Gate C: No fabricated labels; provenance manifest verifiable.
Gate D: Reproducible benchmark (deterministic features + diagnosis pipeline).
Gate E: Calibration + abstention report available and targets met.
"""

import pytest
from src.constants import FEATURE_NAMES, VALID_LABELS
from src.diagnosis.rule_engine import RuleEngine
from src.diagnosis.hybrid_engine import HybridEngine
from src.diagnosis.decision_policy import evaluate_decision
from src.benchmark.calibration import (
    compute_ece,
    compute_false_critical_rate,
    compute_abstention_rate,
    generate_calibration_report,
)


# ---------------------------------------------------------------------------
# Gate A — Zero runtime crashes
# ---------------------------------------------------------------------------

def _all_zero_features():
    return {k: 0.0 for k in FEATURE_NAMES}


@pytest.mark.parametrize(
    "features",
    [
        {},                            # completely empty input
        _all_zero_features(),          # all-zero (healthy flight)
        {"vibe_z_max": 200.0, "vibe_clip_total": 500.0},   # vibration spike
        {"sys_vcc_min": 3.5, "bat_volt_range": 5.0},        # brownout
        {"ekf_vel_var_max": 4.0, "ekf_pos_var_max": 4.0, "ekf_lane_switch_count": 2.0},  # EKF
        {"evt_radio_failsafe_count": 3.0},                  # RC failsafe
        {"motor_saturation_pct": 0.50, "motor_all_high_pct": 0.30, "ctrl_thr_saturated_pct": 0.40},
        {"att_early_divergence": 60.0, "att_time_to_crash_sec": 1.5},  # setup error
        {"mag_field_range": 1200.0, "mag_field_std": 200.0},           # compass
        {k: float("nan") for k in ["vibe_z_max", "mag_field_range"]},  # NaN values
    ],
    ids=[
        "empty", "all_zero", "vibration", "brownout",
        "ekf", "rc_failsafe", "thrust_loss", "setup_error",
        "compass", "nan_values",
    ],
)
def test_gate_a_no_crash_rule_engine(features):
    """Gate A: RuleEngine must never raise an exception."""
    engine = RuleEngine()
    result = engine.diagnose(features)
    assert isinstance(result, list)


@pytest.mark.parametrize(
    "features",
    [
        {},
        _all_zero_features(),
        {"vibe_z_max": 200.0, "vibe_clip_total": 500.0},
        {"sys_vcc_min": 3.5},
    ],
    ids=["empty", "all_zero", "vibration", "brownout"],
)
def test_gate_a_no_crash_hybrid_engine(features):
    """Gate A: HybridEngine must never raise an exception (ML disabled)."""
    engine = HybridEngine()
    engine.ml.available = False
    result = engine.diagnose(features)
    assert isinstance(result, list)


def test_gate_a_decision_policy_no_crash():
    """Gate A: evaluate_decision handles empty and varied inputs without exceptions."""
    for diagnoses in [
        [],
        [{"failure_type": "vibration_high", "confidence": 0.9, "detection_method": "rule"}],
        [{"failure_type": "unknown_type", "confidence": 0.5, "detection_method": "ml"}],
    ]:
        decision = evaluate_decision(diagnoses)
        assert isinstance(decision, dict)
        assert "status" in decision


# ---------------------------------------------------------------------------
# Gate B — Evidence + recommendation in 100% of predictions
# ---------------------------------------------------------------------------

TRIGGERING_FEATURES = [
    {"vibe_z_max": 100.0, "vibe_clip_total": 200.0},
    {"sys_vcc_min": 3.5},
    {"bat_volt_range": 4.0},
    {"gps_nsats_min": 2.0, "gps_fix_pct": 0.6},
    {"motor_spread_max": 800.0, "motor_spread_mean": 500.0},
    {"ekf_vel_var_max": 3.0, "ekf_pos_var_max": 3.0, "ekf_lane_switch_count": 1.0},
    {"evt_radio_failsafe_count": 2.0},
    {"motor_saturation_pct": 0.40, "motor_all_high_pct": 0.25, "ctrl_thr_saturated_pct": 0.35},
    {"att_early_divergence": 55.0, "att_time_to_crash_sec": 1.5},
    {"mag_field_range": 900.0, "mag_field_std": 0.0},
]


def test_gate_b_all_predictions_have_evidence_and_recommendation():
    """Gate B: Every diagnosis from RuleEngine must have evidence and recommendation."""
    engine = RuleEngine()
    for feat in TRIGGERING_FEATURES:
        diagnoses = engine.diagnose(feat)
        for d in diagnoses:
            assert "evidence" in d, f"No evidence in {d}"
            assert len(d["evidence"]) > 0, f"Empty evidence in {d}"
            assert "recommendation" in d, f"No recommendation in {d}"
            assert len(d["recommendation"]) > 0, f"Empty recommendation in {d}"


def test_gate_b_evidence_schema():
    """Gate B: Each evidence item must have feature/value/threshold/direction keys."""
    engine = RuleEngine()
    for feat in TRIGGERING_FEATURES:
        for d in engine.diagnose(feat):
            for ev in d["evidence"]:
                assert "feature" in ev, f"Missing 'feature' in evidence: {ev}"
                assert "value" in ev, f"Missing 'value' in evidence: {ev}"
                assert "threshold" in ev, f"Missing 'threshold' in evidence: {ev}"
                assert "direction" in ev, f"Missing 'direction' in evidence: {ev}"


def test_gate_b_hybrid_evidence_present():
    """Gate B: HybridEngine (rule-only) must also include evidence."""
    engine = HybridEngine()
    engine.ml.available = False
    for feat in TRIGGERING_FEATURES:
        for d in engine.diagnose(feat):
            assert "evidence" in d
            assert len(d["evidence"]) > 0


# ---------------------------------------------------------------------------
# Gate C — No fabricated labels; VALID_LABELS are the only used labels
# ---------------------------------------------------------------------------

def test_gate_c_all_rule_outputs_use_valid_labels():
    """Gate C: Rule engine only emits labels that are in VALID_LABELS."""
    engine = RuleEngine()
    for feat in TRIGGERING_FEATURES:
        for d in engine.diagnose(feat):
            assert d["failure_type"] in VALID_LABELS, (
                f"Unknown label '{d['failure_type']}' emitted by RuleEngine"
            )


def test_gate_c_valid_labels_are_canonical():
    """Gate C: VALID_LABELS contains at least 14 labels covering all diagnosed types."""
    assert len(VALID_LABELS) >= 14
    required = {
        "healthy", "vibration_high", "compass_interference", "power_instability",
        "gps_quality_poor", "motor_imbalance", "ekf_failure", "mechanical_failure",
        "brownout", "pid_tuning_issue", "rc_failsafe", "crash_unknown",
        "thrust_loss", "setup_error",
    }
    assert required.issubset(set(VALID_LABELS))


# ---------------------------------------------------------------------------
# Gate D — Reproducible benchmark (deterministic pipeline)
# ---------------------------------------------------------------------------

def test_gate_d_diagnosis_is_deterministic():
    """Gate D: Two separate RuleEngine instances produce identical results for the same input."""
    features = {
        "vibe_z_max": 85.0,
        "vibe_clip_total": 150.0,
        "mag_field_range": 700.0,
        "motor_spread_max": 850.0,
        "motor_spread_mean": 450.0,
    }
    engine_a = RuleEngine()
    engine_b = RuleEngine()
    result_a = engine_a.diagnose(features)
    result_b = engine_b.diagnose(features)

    assert len(result_a) == len(result_b), "Diagnoses list lengths differ between runs"
    for da, db in zip(result_a, result_b):
        assert da["failure_type"] == db["failure_type"]
        assert abs(da["confidence"] - db["confidence"]) < 1e-9


def test_gate_d_hybrid_deterministic():
    """Gate D: HybridEngine is deterministic for same input (ML disabled)."""
    features = {"vibe_z_max": 90.0, "vibe_clip_total": 200.0}
    engine = HybridEngine()
    engine.ml.available = False

    results = [engine.diagnose(features) for _ in range(3)]
    for r in results[1:]:
        assert len(r) == len(results[0])
        for d1, d2 in zip(results[0], r):
            assert d1["failure_type"] == d2["failure_type"]
            assert d1["confidence"] == d2["confidence"]


# ---------------------------------------------------------------------------
# Gate E — Calibration + abstention report
# ---------------------------------------------------------------------------

def test_gate_e_ece_computation_basic():
    """Gate E: compute_ece returns 0 for perfectly calibrated predictor."""
    # Perfect calibration: confidence=1 → all correct
    confs = [1.0, 1.0, 1.0, 1.0]
    correct = [True, True, True, True]
    assert compute_ece(confs, correct) == pytest.approx(0.0, abs=1e-9)


def test_gate_e_ece_worst_case():
    """Gate E: compute_ece returns ~1 for worst-case (100% confidence, 0% accuracy)."""
    confs = [0.99] * 10
    correct = [False] * 10
    ece = compute_ece(confs, correct)
    assert ece > 0.8


def test_gate_e_ece_empty_input():
    """Gate E: compute_ece handles empty input gracefully."""
    assert compute_ece([], []) == 0.0


def test_gate_e_fcr_all_healthy_no_critical():
    """Gate E / P4-03: FCR = 0 when engine makes no critical errors on healthy logs."""
    results = [
        {"ground_truth": ["healthy"], "predicted": []},
        {"ground_truth": ["healthy"], "predicted": [{"failure_type": "vibration_high", "confidence": 0.3, "severity": "info"}]},
    ]
    assert compute_false_critical_rate(results) == pytest.approx(0.0)


def test_gate_e_fcr_detects_false_critical():
    """Gate E / P4-03: FCR correctly counts critical diagnoses on healthy logs."""
    results = [
        {"ground_truth": ["healthy"], "predicted": [{"failure_type": "vibration_high", "confidence": 0.9, "severity": "critical"}]},
        {"ground_truth": ["healthy"], "predicted": []},
        {"ground_truth": ["vibration_high"], "predicted": [{"failure_type": "vibration_high", "confidence": 0.9, "severity": "critical"}]},
    ]
    # 1 out of 2 healthy logs triggered critical → FCR = 0.50
    assert compute_false_critical_rate(results) == pytest.approx(0.50)


def test_gate_e_fcr_target_met_on_rule_engine():
    """Gate E / P4-03: RuleEngine FCR <= 10% on synthetic healthy flight features."""
    engine = RuleEngine()
    # Simulate 20 "healthy" flights with benign but realistic parameters
    healthy_profiles = [
        {"bat_volt_min": 22.0, "sys_vcc_min": 5.1, "gps_nsats_min": 10.0, "gps_fix_pct": 1.0, "bat_margin": 8.0},
        {"bat_volt_min": 24.0, "sys_vcc_min": 5.2, "gps_nsats_min": 12.0, "gps_fix_pct": 1.0, "bat_margin": 12.0},
        {k: 0.0 for k in FEATURE_NAMES},
    ] * 7  # 21 healthy profiles

    results = []
    for profile in healthy_profiles:
        preds = engine.diagnose(profile)
        results.append({"ground_truth": ["healthy"], "predicted": preds})

    fcr = compute_false_critical_rate(results)
    assert fcr <= 0.10, (
        f"False-Critical Rate {fcr:.2%} exceeds 10% target on healthy flight profiles"
    )


def test_gate_e_abstention_rate():
    """Gate E: abstention rate is correctly computed from decision outputs."""
    decisions = [
        {"status": "confirmed", "requires_human_review": False},
        {"status": "uncertain", "requires_human_review": True},
        {"status": "healthy", "requires_human_review": False},
    ]
    rate = compute_abstention_rate(decisions)
    assert rate == pytest.approx(1 / 3, abs=1e-6)


def test_gate_e_calibration_report_structure():
    """Gate E: generate_calibration_report returns all required keys."""
    results = [
        {"ground_truth": ["vibration_high"], "predicted": [{"failure_type": "vibration_high", "confidence": 0.9, "severity": "critical"}]},
        {"ground_truth": ["healthy"], "predicted": []},
    ]
    report = generate_calibration_report(results)

    required_keys = {"n_samples", "n_healthy", "ece", "abstention_rate", "false_critical_rate", "target_met"}
    assert required_keys.issubset(report.keys())
    assert isinstance(report["ece"], float)
    assert 0.0 <= report["false_critical_rate"] <= 1.0
    assert "ece_le_0.08" in report["target_met"]
    assert "fcr_le_0.10" in report["target_met"]


def test_gate_e_healthy_only_no_false_positives():
    """Gate E / P4-03: Engine produces no critical alerts for completely benign input."""
    engine = RuleEngine()
    features = {
        "bat_volt_min": 22.2, "sys_vcc_min": 5.1, "bat_volt_range": 0.5,
        "gps_nsats_min": 11.0, "gps_fix_pct": 1.0, "bat_margin": 9.0,
        "vibe_z_max": 15.0, "vibe_clip_total": 0.0,
        "mag_field_range": 100.0, "mag_field_std": 10.0,
        "motor_spread_max": 150.0, "motor_spread_mean": 80.0,
        "ekf_vel_var_max": 0.2, "ekf_pos_var_max": 0.2,
    }
    diagnoses = engine.diagnose(features)
    critical = [d for d in diagnoses if d["severity"] == "critical"]
    assert len(critical) == 0, (
        f"Critical alerts on benign healthy flight: {[d['failure_type'] for d in critical]}"
    )
