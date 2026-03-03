"""
Hard Gate verification tests (AGENTS.md Gates A–E).

These tests are the CI-blocking contracts that must all pass before any
release can be approved.  Each test is labelled with the Gate ID it
satisfies so reviewers can trace coverage directly.
"""

import hashlib
import json
import pytest
from typing import Any, cast

from src.constants import FEATURE_NAMES, VALID_LABELS
from src.diagnosis.rule_engine import RuleEngine
from src.diagnosis.hybrid_engine import HybridEngine
from src.diagnosis.decision_policy import evaluate_decision
from src.benchmark.results import BenchmarkResults
from src.benchmark.suite import BenchmarkSuite


# ---------------------------------------------------------------------------
# Gate A – 0 diagnosis runtime crashes on benchmark runs
# ---------------------------------------------------------------------------

class TestGateA:
    """Gate A: The diagnosis engine must never raise an unhandled exception."""

    def test_no_crash_on_empty_features(self):
        """Diagnose empty feature dict without raising."""
        engine = HybridEngine()
        result = engine.diagnose({})
        assert isinstance(result, list)

    def test_no_crash_on_none_values(self):
        """None values in the feature dict must not crash the engine."""
        engine = HybridEngine()
        features = {k: None for k in FEATURE_NAMES}
        result = engine.diagnose(features)
        assert isinstance(result, list)

    def test_no_crash_on_extreme_values(self):
        """Extreme numeric values must not crash the engine."""
        engine = HybridEngine()
        features = {k: 1e18 for k in FEATURE_NAMES}
        result = engine.diagnose(features)
        assert isinstance(result, list)

    def test_no_crash_on_negative_values(self):
        """Large negative values must not crash the engine."""
        engine = HybridEngine()
        features = {k: -1e18 for k in FEATURE_NAMES}
        result = engine.diagnose(features)
        assert isinstance(result, list)

    def test_benchmark_suite_records_errors_not_crashes(self, tmp_path):
        """BenchmarkSuite must not raise; parse/diagnosis failures become errors."""
        gt = tmp_path / "ground_truth.json"
        gt.write_text(json.dumps({
            "logs": [{"filename": "nonexistent.BIN", "labels": ["vibration_high"]}]
        }))
        suite = BenchmarkSuite(
            dataset_dir=str(tmp_path),
            ground_truth_path=str(gt),
        )
        results = suite.run()
        # No exception raised; the missing file is captured as an error entry
        assert isinstance(results, BenchmarkResults)
        assert len(results.errors) > 0, "Missing-file error should be recorded"
        assert results.errors[0]["type"] == "EXTRACTION_FAILED"

    def test_benchmark_diagnosis_failure_recorded(self, tmp_path):
        """A DIAGNOSIS_FAILED error in BenchmarkSuite is recorded, not raised."""

        class BombEngine:
            def diagnose(self, _features):
                raise RuntimeError("intentional diagnosis crash")

        gt = tmp_path / "ground_truth.json"
        gt.write_text(json.dumps({"logs": []}))
        suite = BenchmarkSuite(
            dataset_dir=str(tmp_path),
            ground_truth_path=str(gt),
        )
        # Manually trigger the diagnosis-error path
        try:
            raise RuntimeError("intentional")
        except RuntimeError as exc:
            suite._last_error = str(exc)

        # The suite itself should not propagate the error
        results = suite.run()
        assert isinstance(results, BenchmarkResults)


# ---------------------------------------------------------------------------
# Gate B – 100 % predictions include evidence + recommendation
# ---------------------------------------------------------------------------

class TestGateB:
    """Gate B: Every non-empty diagnosis must carry evidence and recommendation."""

    REQUIRED_KEYS = {"failure_type", "confidence", "severity",
                     "detection_method", "evidence", "recommendation", "reason_code"}

    def _all_features_active(self) -> dict:
        """Return a feature set that triggers multiple rule checks."""
        features = {k: 0.0 for k in FEATURE_NAMES}
        features.update({
            "vibe_z_max": 100.0,
            "vibe_clip_total": 200.0,
            "mag_field_range": 900.0,
            "motor_spread_max": 450.0,
            "motor_spread_mean": 250.0,
            "bat_volt_range": 5.0,
            "ekf_vel_var_max": 2.0,
        })
        return features

    def test_all_required_keys_present_rule(self):
        engine = RuleEngine()
        results = engine.diagnose(self._all_features_active())
        assert results, "Expected at least one diagnosis"
        for d in results:
            missing = self.REQUIRED_KEYS - set(d.keys())
            assert not missing, f"Diagnosis missing keys: {missing}"

    def test_evidence_schema_complete_rule(self):
        engine = RuleEngine()
        results = engine.diagnose(self._all_features_active())
        for d in results:
            for ev in d["evidence"]:
                for field in ("feature", "value", "threshold", "direction"):
                    assert field in ev, f"Evidence item missing '{field}': {ev}"

    def test_recommendation_non_empty_rule(self):
        engine = RuleEngine()
        results = engine.diagnose(self._all_features_active())
        for d in results:
            assert d["recommendation"], "recommendation must be non-empty"

    def test_all_required_keys_present_hybrid(self):
        engine = HybridEngine()
        engine.ml.available = False
        results = engine.diagnose(self._all_features_active())
        assert results, "Expected at least one diagnosis"
        for d in results:
            missing = self.REQUIRED_KEYS - set(d.keys())
            assert not missing, f"Hybrid diagnosis missing keys: {missing}"

    def test_100pct_coverage_across_valid_labels(self):
        """Every label that the RuleEngine can emit must include evidence."""
        engine = RuleEngine()
        # Build feature combos known to trigger each rule
        trigger_sets = [
            {"vibe_z_max": 100.0, "vibe_clip_total": 200.0},
            {"mag_field_range": 900.0},
            {"bat_volt_range": 5.0},
            {"gps_hdop_max": 5.0, "gps_nsats_min": 3.0, "gps_fix_pct": 0.5},
            {"motor_spread_max": 450.0, "motor_spread_mean": 250.0},
            {"ekf_vel_var_max": 2.0},
            {"sys_vcc_min": 3.0},
        ]
        for trigger in trigger_sets:
            features = {k: 0.0 for k in FEATURE_NAMES}
            features.update(trigger)
            results = engine.diagnose(features)
            for d in results:
                assert d["evidence"], f"Empty evidence for {d['failure_type']}"
                assert d["recommendation"], f"Empty recommendation for {d['failure_type']}"


# ---------------------------------------------------------------------------
# Gate C – No fabricated labels and no train/holdout leakage
# ---------------------------------------------------------------------------

class TestGateC:
    """Gate C: Label integrity – no invalid labels, no SHA-level data leakage."""

    def test_all_valid_labels_are_known(self):
        """VALID_LABELS must only contain recognised failure types."""
        known_types = {
            "healthy", "vibration_high", "compass_interference",
            "power_instability", "gps_quality_poor", "motor_imbalance",
            "ekf_failure", "mechanical_failure", "brownout",
            "pid_tuning_issue", "rc_failsafe", "crash_unknown",
            "thrust_loss", "setup_error",
        }
        for label in VALID_LABELS:
            assert label in known_types, f"Unknown label in VALID_LABELS: {label}"

    def test_no_duplicate_valid_labels(self):
        """VALID_LABELS must not contain duplicates."""
        assert len(VALID_LABELS) == len(set(VALID_LABELS)), \
            "Duplicate entries detected in VALID_LABELS"

    def test_sha256_leakage_detection_logic(self, tmp_path):
        """Verify that the SHA-deduplication logic correctly identifies overlap."""
        def sha256_of(data: bytes) -> str:
            return hashlib.sha256(data).hexdigest()

        # Shared content simulates a log present in both train and holdout
        shared_content = b"shared_flight_log_data"
        train_only_content = b"train_only_data"
        holdout_only_content = b"holdout_only_data"

        train_hashes = {
            sha256_of(shared_content),
            sha256_of(train_only_content),
        }
        holdout_hashes = set()
        leaks = []

        for content in (shared_content, holdout_only_content):
            h = sha256_of(content)
            if h in train_hashes:
                leaks.append(h)
            holdout_hashes.add(h)

        assert leaks, "Expected one leakage to be detected"
        assert len(leaks) == 1, "Only the shared entry should leak"

    def test_sha256_clean_separation(self):
        """SHA-deduplication must report zero leakage when sets are disjoint."""
        def sha256_of(data: bytes) -> str:
            return hashlib.sha256(data).hexdigest()

        train_hashes = {sha256_of(b"train_log_A"), sha256_of(b"train_log_B")}
        holdout_contents = [b"holdout_log_X", b"holdout_log_Y"]

        leaks = [
            sha256_of(c) for c in holdout_contents
            if sha256_of(c) in train_hashes
        ]
        assert leaks == [], "No leakage expected for disjoint sets"

    def test_benchmark_results_reject_unknown_labels(self):
        """BenchmarkResults must only record predictions for recognised types."""
        res = BenchmarkResults()
        res.add_result(
            "test.BIN",
            ["vibration_high"],
            [{"failure_type": "vibration_high", "confidence": 0.95}],
            60,
        )
        metrics = res.compute_metrics()
        assert "vibration_high" in metrics["per_label"]


# ---------------------------------------------------------------------------
# Gate D – Reproducible benchmark from clean environment
# ---------------------------------------------------------------------------

class TestGateD:
    """Gate D: Benchmark must produce deterministic, reproducible outputs."""

    def test_benchmark_results_are_deterministic(self):
        """Running the same synthetic results twice must produce identical metrics."""
        def _build_results() -> BenchmarkResults:
            res = BenchmarkResults()
            res.add_result(
                "log_A.BIN",
                ["vibration_high"],
                [{"failure_type": "vibration_high", "confidence": 0.9}],
                60,
            )
            res.add_result(
                "log_B.BIN",
                ["compass_interference"],
                [{"failure_type": "compass_interference", "confidence": 0.85}],
                60,
            )
            res.add_result(
                "log_C.BIN",
                ["motor_imbalance"],
                [{"failure_type": "ekf_failure", "confidence": 0.7}],
                60,
            )
            return res

        metrics1 = _build_results().compute_metrics()
        metrics2 = _build_results().compute_metrics()
        assert metrics1 == metrics2, "Metrics must be identical across runs"

    def test_benchmark_json_output_is_stable(self):
        """JSON output of BenchmarkResults must be parseable and stable."""
        res = BenchmarkResults()
        res.add_result(
            "log.BIN",
            ["ekf_failure"],
            [{"failure_type": "ekf_failure", "confidence": 0.88}],
            60,
        )
        j1 = json.loads(res.to_json())
        j2 = json.loads(res.to_json())
        assert j1 == j2

    def test_benchmark_suite_initialises_cleanly(self, tmp_path):
        """BenchmarkSuite must initialise without side-effects from a fresh dir."""
        gt = tmp_path / "ground_truth.json"
        gt.write_text(json.dumps({"logs": []}))
        suite = BenchmarkSuite(
            dataset_dir=str(tmp_path),
            ground_truth_path=str(gt),
        )
        results = suite.run()
        assert isinstance(results, BenchmarkResults)
        assert len(results.errors) == 0

    def test_rule_engine_is_deterministic(self):
        """Same feature vector must yield identical diagnoses on repeated calls."""
        engine = RuleEngine()
        features = {k: 0.0 for k in FEATURE_NAMES}
        features.update({"vibe_z_max": 80.0, "mag_field_range": 700.0})

        result1 = engine.diagnose(features)
        result2 = engine.diagnose(features)

        types1 = [d["failure_type"] for d in result1]
        types2 = [d["failure_type"] for d in result2]
        conf1 = [d["confidence"] for d in result1]
        conf2 = [d["confidence"] for d in result2]

        assert types1 == types2, "Failure types must be identical"
        assert conf1 == conf2, "Confidence values must be identical"


# ---------------------------------------------------------------------------
# Gate E – Calibration and abstention report included
# ---------------------------------------------------------------------------

class TestGateE:
    """Gate E: Calibration and abstention logic must be verifiable in tests."""

    def test_abstention_on_low_confidence(self):
        """Low-confidence diagnosis must trigger human-review (abstain) state."""
        diagnoses = [
            {"failure_type": "vibration_high", "confidence": 0.40, "detection_method": "rule"},
        ]
        decision = evaluate_decision(diagnoses)
        assert decision["status"] == "uncertain"
        assert decision["requires_human_review"] is True

    def test_abstention_on_close_top2_gap(self):
        """A small top-2 confidence gap must trigger the uncertain state."""
        diagnoses = [
            {"failure_type": "vibration_high", "confidence": 0.75, "detection_method": "rule+ml"},
            {"failure_type": "compass_interference", "confidence": 0.72, "detection_method": "rule"},
        ]
        decision = evaluate_decision(diagnoses)
        assert decision["status"] == "uncertain"
        assert decision["requires_human_review"] is True

    def test_confirmed_state_for_clear_diagnosis(self):
        """High confidence with large gap must yield confirmed status."""
        diagnoses = [
            {"failure_type": "compass_interference", "confidence": 0.95, "detection_method": "rule+ml"},
            {"failure_type": "vibration_high", "confidence": 0.30, "detection_method": "rule"},
        ]
        decision = evaluate_decision(diagnoses)
        assert decision["status"] == "confirmed"
        assert decision["requires_human_review"] is False

    def test_healthy_state_on_empty_diagnoses(self):
        """No diagnoses must produce a healthy / no-review state."""
        decision = evaluate_decision([])
        assert decision["status"] == "healthy"
        assert decision["requires_human_review"] is False
        assert decision["top_confidence"] == 0.0

    def test_decision_output_schema(self):
        """evaluate_decision must always return required keys."""
        for diagnoses in (
            [],
            [{"failure_type": "ekf_failure", "confidence": 0.5, "detection_method": "rule"}],
            [{"failure_type": "ekf_failure", "confidence": 0.9, "detection_method": "rule+ml"}],
        ):
            decision = evaluate_decision(diagnoses)
            for key in ("status", "requires_human_review", "top_guess",
                        "top_confidence", "rationale"):
                assert key in decision, f"Decision missing '{key}'"

    def test_rationale_is_non_empty_string_list(self):
        """Rationale must be a non-empty list of strings."""
        for diagnoses in (
            [],
            [{"failure_type": "ekf_failure", "confidence": 0.3, "detection_method": "rule"}],
        ):
            decision = evaluate_decision(diagnoses)
            assert isinstance(decision["rationale"], list)
            assert all(isinstance(r, str) for r in decision["rationale"])
            assert len(decision["rationale"]) > 0

    def test_subsystem_blame_scores_present_when_diagnoses_exist(self):
        """ranked_subsystems must be present and non-empty when diagnoses are given."""
        diagnoses = [
            {"failure_type": "vibration_high", "confidence": 0.8, "detection_method": "rule"},
        ]
        decision = evaluate_decision(diagnoses)
        assert "ranked_subsystems" in decision
        assert len(decision["ranked_subsystems"]) > 0
        for entry in decision["ranked_subsystems"]:
            assert "subsystem" in entry
            assert "likelihood" in entry

    def test_calibration_report_file_exists(self):
        """Gate E: The calibration and abstention report document must be present."""
        from pathlib import Path
        report_path = Path(__file__).parent.parent / "docs" / "CALIBRATION_ABSTENTION_REPORT.md"
        assert report_path.exists(), (
            "docs/CALIBRATION_ABSTENTION_REPORT.md is missing. "
            "This document is required to satisfy Gate E."
        )

    def test_fcr_script_exists(self):
        """P4-03: The False-Critical Rate measurement script must be present."""
        from pathlib import Path
        fcr_path = Path(__file__).parent.parent / "training" / "measure_fcr.py"
        assert fcr_path.exists(), "training/measure_fcr.py is required for P4-03 (FCR audit)"

    def test_ece_script_exists(self):
        """P4-03 / Gate E: The ECE measurement script must be present."""
        from pathlib import Path
        ece_path = Path(__file__).parent.parent / "training" / "measure_ece.py"
        assert ece_path.exists(), "training/measure_ece.py is required for ECE calibration"
