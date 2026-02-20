import pytest
import json
import os
from src.benchmark.suite import BenchmarkSuite
from src.benchmark.results import BenchmarkResults

def test_multi_label_comparison():
    res = BenchmarkResults()
    res.add_result("log1.BIN", ["vibration_high", "motor_imbalance"], 
                   [{"failure_type": "vibration_high", "confidence": 0.9}, {"failure_type": "compass_interference", "confidence": 0.8}], 60)
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
    res.add_result("log1.BIN", ["healthy"], [{"failure_type": "healthy", "confidence": 0.9}], 60)
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
