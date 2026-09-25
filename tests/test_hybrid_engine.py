from pathlib import Path
from typing import Any, cast

from src.diagnosis.hybrid_engine import HybridEngine


def test_hybrid_engine_keeps_critical_rule_only_secondary():
    class StubRuleEngine:
        def diagnose(self, _features):
            return [
                {"failure_type": "compass_interference", "confidence": 0.65, "evidence": [], "severity": "critical"},
                {"failure_type": "motor_imbalance", "confidence": 1.0, "evidence": [], "severity": "critical"},
            ]

    class StubMLClassifier:
        available = True

        def predict(self, _features):
            return [{"failure_type": "compass_interference", "confidence": 0.70, "evidence": []}]

    engine = HybridEngine(
        rule_engine=cast(Any, StubRuleEngine()),
        ml_classifier=cast(Any, StubMLClassifier()),
    )
    result = engine.diagnose({})
    assert "motor_imbalance" in [diag["failure_type"] for diag in result]


def test_hybrid_engine_returns_empty_without_rule_or_ml_hits():
    class StubRuleEngine:
        def diagnose(self, _features):
            return []

    class StubMLClassifier:
        available = False

        def predict(self, _features):
            return []

    engine = HybridEngine(
        rule_engine=cast(Any, StubRuleEngine()),
        ml_classifier=cast(Any, StubMLClassifier()),
    )
    assert engine.diagnose({}) == []


def test_hybrid_engine_emits_hypothesis_scaffolding():
    class StubRuleEngine:
        def diagnose(self, _features):
            return [
                {
                    "failure_type": "thrust_loss",
                    "confidence": 0.9,
                    "evidence": [{"feature": "motor_saturation_pct", "value": 0.5, "threshold": 0.25}],
                    "severity": "critical",
                    "detection_method": "rule",
                    "recommendation": "Check propulsion limits.",
                    "reason_code": "confirmed",
                },
                {
                    "failure_type": "ekf_failure",
                    "confidence": 0.75,
                    "evidence": [{"feature": "ekf_pos_var_max", "value": 2.0, "threshold": 1.5}],
                    "severity": "warning",
                    "detection_method": "rule",
                    "recommendation": "Check upstream sensors.",
                    "reason_code": "confirmed",
                },
            ]

    class StubMLClassifier:
        available = False

        def predict(self, _features):
            return []

    engine = HybridEngine(
        rule_engine=cast(Any, StubRuleEngine()),
        ml_classifier=cast(Any, StubMLClassifier()),
    )
    engine.diagnose(
        {
            "_thrust_loss_tanomaly": 13_000_000.0,
            "ekf_pos_var_tanomaly": 16_000_000.0,
        }
    )
    explain = engine.last_explain_data
    assert explain["hypotheses"][0]["failure_type"] == "thrust_loss"
    assert "preceded" in explain["causal_arbiter"]["reason"]


def test_hybrid_engine_uses_raw_window_aggregation_when_available():
    class StubRuleEngine:
        def diagnose(self, _features):
            return []

    class StubMLClassifier:
        available = True
        feature_columns = []
        last_prediction_info = {"aggregation": "max_raw_probability", "candidate_count": 2}

        def predict(self, _features):
            raise AssertionError("window aggregation should be used")

        def predict_windows(self, windows, _context):
            assert len(windows) == 2
            return [
                {
                    "failure_type": "vibration_high",
                    "confidence": 0.8,
                    "evidence": [],
                    "severity": "critical",
                    "detection_method": "ml",
                    "recommendation": "Inspect vibration.",
                }
            ]

    class StubAnomalyDetector:
        available = False

    engine = HybridEngine(
        rule_engine=cast(Any, StubRuleEngine()),
        ml_classifier=cast(Any, StubMLClassifier()),
        anomaly_detector=cast(Any, StubAnomalyDetector()),
    )
    result = engine.diagnose({}, window_features=[{}, {}])

    assert result[0]["failure_type"] == "vibration_high"
    assert engine.last_explain_data["ml_aggregation"]["candidate_count"] == 2


def test_hybrid_engine_loads_anomaly_artifact_from_ml_model_directory(
    monkeypatch, tmp_path
):
    captured: dict[str, Path] = {}

    class StubRuleEngine:
        def diagnose(self, _features):
            return []

    class StubMLClassifier:
        available = False
        model_path = str(tmp_path / "candidate" / "classifier.joblib")

        def predict(self, _features):
            return []

    class CapturingAnomalyDetector:
        available = False

        def __init__(self, model_path):
            captured["model_path"] = Path(model_path)

    monkeypatch.setattr(
        "src.diagnosis.hybrid_engine.AnomalyDetector", CapturingAnomalyDetector
    )
    HybridEngine(
        rule_engine=cast(Any, StubRuleEngine()),
        ml_classifier=cast(Any, StubMLClassifier()),
    )

    assert captured["model_path"] == tmp_path / "candidate" / "anomaly_detector.joblib"


class _TimedRuleEngine:
    """Early low-confidence motor signal, late high-confidence compass signal."""

    def diagnose(self, _features):
        return [
            {"failure_type": "motor_imbalance", "confidence": 0.70, "evidence": [], "severity": "warning"},
            {"failure_type": "compass_interference", "confidence": 0.95, "evidence": [], "severity": "warning"},
        ]


class _NoML:
    available = False

    def predict(self, _features):
        return []


_TIMED_FEATURES = {"motor_spread_tanomaly": 10_000_000.0, "mag_tanomaly": 100_000_000.0}


def _timed_engine(**kwargs):
    return HybridEngine(
        rule_engine=cast(Any, _TimedRuleEngine()),
        ml_classifier=cast(Any, _NoML()),
        **kwargs,
    )


def test_temporal_arbitration_selects_earliest_onset_by_default():
    result = _timed_engine().diagnose(cast(Any, dict(_TIMED_FEATURES)))
    assert result[0]["failure_type"] == "motor_imbalance"
    assert result[0]["recommendation"].startswith("[ARB]")


def test_temporal_arbitration_can_be_disabled_for_ablation():
    engine = _timed_engine(temporal_arbitration=False)
    result = engine.diagnose(cast(Any, dict(_TIMED_FEATURES)))
    assert result[0]["failure_type"] == "compass_interference"
    assert engine.last_explain_data["causal_arbiter"]["reason"].startswith("selected by merged")


def test_explicit_defaults_match_production_behaviour():
    features = cast(Any, dict(_TIMED_FEATURES))
    default = _timed_engine().diagnose(features)
    explicit = _timed_engine(
        temporal_arbitration=True,
        tie_window_s=5.0,
        proximity_window_s=30.0,
        extreme_confidence=0.85,
        ml_weight=0.65,
        single_source_discount=0.85,
    ).diagnose(features)
    assert default == explicit


def test_wide_proximity_window_lets_extreme_confidence_override_onset():
    # rule-only merged confidences are 0.595 and 0.8075; lower the extreme
    # threshold and widen the window so the later, much stronger signal wins.
    engine = _timed_engine(proximity_window_s=120.0, extreme_confidence=0.8)
    result = engine.diagnose(cast(Any, dict(_TIMED_FEATURES)))
    assert result[0]["failure_type"] == "compass_interference"


def test_invalid_fusion_settings_are_rejected():
    import pytest

    with pytest.raises(ValueError):
        _timed_engine(ml_weight=1.5)
    with pytest.raises(ValueError):
        _timed_engine(tie_window_s=-1.0)


def test_benchmark_suite_builds_no_cita_ablation_engine(tmp_path):
    import json

    from src.benchmark.suite import BenchmarkSuite

    gt = tmp_path / "ground_truth.json"
    gt.write_text(json.dumps({"logs": []}))
    suite = BenchmarkSuite(
        dataset_dir=str(tmp_path), ground_truth_path=str(gt), engine="hybrid_no_cita"
    )
    assert isinstance(suite.engine, HybridEngine)
    assert suite.engine.temporal_arbitration is False


def test_tied_diagnoses_resolve_identically_across_hash_seeds():
    """Exact ties must not depend on Python's per-process set ordering."""
    import os
    import subprocess
    import sys

    script = (
        "from typing import Any, cast\n"
        "from src.diagnosis.hybrid_engine import HybridEngine\n"
        "class R:\n"
        "    def diagnose(self, _f):\n"
        "        return [{'failure_type': t, 'confidence': 0.8, 'evidence': [],"
        " 'severity': 'warning'} for t in ('power_instability', 'ekf_failure',"
        " 'gps_quality_poor')]\n"
        "class M:\n"
        "    available = False\n"
        "    def predict(self, _f):\n"
        "        return []\n"
        "e = HybridEngine(rule_engine=cast(Any, R()), ml_classifier=cast(Any, M()),"
        " temporal_arbitration=False)\n"
        "print([d['failure_type'] for d in e.diagnose({})])\n"
    )
    root = Path(__file__).resolve().parents[1]
    outputs = set()
    for seed in ("1", "2", "3", "4", "5"):
        env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": str(root)}
        result = subprocess.run(
            [sys.executable, "-c", script], cwd=root, env=env, capture_output=True, text=True
        )
        assert result.returncode == 0, result.stderr
        outputs.add(result.stdout.strip())
    assert len(outputs) == 1, outputs
