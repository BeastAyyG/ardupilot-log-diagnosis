from src.benchmark.results import BenchmarkResults


def test_benchmark_uses_honest_metric_names():
    results = BenchmarkResults()
    results.add_result(
        "flight.BIN",
        ["vibration_high"],
        [{"failure_type": "vibration_high", "confidence": 0.9, "severity": "critical", "detection_method": "rule", "evidence": [], "recommendation": "x", "reason_code": "confirmed"}],
        1,
    )
    metrics = results.compute_metrics()

    assert "any_match_accuracy" in metrics["overall"]
    assert "accuracy" not in metrics["overall"]


def test_benchmark_markdown_labels_match_metric_meaning():
    results = BenchmarkResults()
    results.add_result(
        "flight.BIN",
        ["vibration_high"],
        [{"failure_type": "vibration_high", "confidence": 0.9, "severity": "critical", "detection_method": "rule", "evidence": [], "recommendation": "x", "reason_code": "confirmed"}],
        1,
    )
    markdown = results.to_markdown()

    assert "Any-Match Accuracy" in markdown
    assert "Exact Match Accuracy" not in markdown
    assert "Exact-Match Accuracy" in markdown
