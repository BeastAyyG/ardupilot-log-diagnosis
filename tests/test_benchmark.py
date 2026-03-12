import json
from typing import cast

from src.benchmark.suite import BenchmarkSuite
from src.benchmark.results import BenchmarkResults
from src.contracts import DiagnosisDict


def _diag(label, confidence) -> DiagnosisDict:
    return cast(DiagnosisDict, {
        "failure_type": label,
        "confidence": confidence,
        "severity": "critical",
        "detection_method": "rule",
        "evidence": [],
        "recommendation": "test",
        "reason_code": "confirmed",
    })

def test_multi_label_comparison():
    res = BenchmarkResults()
    res.add_result(
        "log1.BIN",
        ["vibration_high", "motor_imbalance"],
        [_diag("vibration_high", 0.9), _diag("compass_interference", 0.8)],
        60,
    )
    metrics = res.compute_metrics()
    assert metrics["per_label"]["vibration_high"]["tp"] == 1
    assert metrics["per_label"]["vibration_high"]["fn"] == 0
    assert metrics["per_label"]["motor_imbalance"]["fn"] == 1
    assert metrics["per_label"]["compass_interference"]["fp"] == 1

def test_missing_bin_handled(tmp_path):
    gt = tmp_path / "ground_truth.json"
    gt.write_text(json.dumps({"logs": [{"filename": "missing.BIN", "labels": []}]}))
    suite = BenchmarkSuite(dataset_dir=str(tmp_path), ground_truth_path=str(gt))
    res = suite.run()
    assert len(res.errors) > 0 
    assert res.errors[0]["type"] == "EXTRACTION_FAILED"

def test_metrics_computation():
    res = BenchmarkResults()
    res.add_result("log1.BIN", ["healthy"], [_diag("healthy", 0.9)], 60)
    metrics = res.compute_metrics()
    assert metrics["per_label"]["healthy"]["tp"] == 1
    assert metrics["per_label"]["healthy"]["f1"] == 1.0

def test_empty_dataset(tmp_path):
    gt = tmp_path / "ground_truth.json"
    gt.write_text(json.dumps({"logs": []}))
    suite = BenchmarkSuite(dataset_dir=str(tmp_path), ground_truth_path=str(gt))
    res = suite.run()
    assert len(res.errors) == 0

def test_json_output_valid():
    res = BenchmarkResults()
    j = res.to_json()
    assert isinstance(json.loads(j), dict)

def test_markdown_output():
    res = BenchmarkResults()
    md = res.to_markdown()
    assert "# Benchmark Results" in md


def test_benchmark_skips_logs_with_failed_extraction(monkeypatch, tmp_path):
    gt = tmp_path / "ground_truth.json"
    log_path = tmp_path / "flight.BIN"
    gt.write_text(json.dumps({"logs": [{"filename": "flight.BIN", "labels": ["vibration_high"]}]}))
    log_path.write_bytes(b"dummy")

    class FakeParser:
        def __init__(self, _filepath):
            pass

        def parse(self):
            return {"messages": {"VIBE": [{}]}, "metadata": {}}

    class FakePipeline:
        def extract(self, _parsed):
            return {"_metadata": {"extraction_success": False}}

    monkeypatch.setattr("src.benchmark.suite.LogParser", FakeParser)
    monkeypatch.setattr("src.benchmark.suite.FeaturePipeline", FakePipeline)

    suite = BenchmarkSuite(dataset_dir=str(tmp_path), ground_truth_path=str(gt))
    result = suite.run()
    assert result.errors
    assert result.errors[0]["type"] == "EXTRACTION_FAILED"
