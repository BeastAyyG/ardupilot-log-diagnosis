from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

from benchmarks.acceptance import (
    TARGETS,
    benchmark_batch,
    benchmark_diagnostic,
    benchmark_ingestion,
    benchmark_memory,
    benchmark_sitl,
    environment_snapshot,
    write_synthetic_arrow,
)
from benchmarks.diagnostic import DIAGNOSTIC_MODULES


def test_synthetic_arrow_workload_is_deterministic_and_size_checked(tmp_path):
    first = tmp_path / "first.arrow"
    second = tmp_path / "second.arrow"
    first_info = write_synthetic_arrow(first, target_bytes=1_000_000)
    second_info = write_synthetic_arrow(second, target_bytes=1_000_000)

    assert first_info["synthetic"] is True
    assert first_info["bytes"] >= 1_000_000
    assert first_info["rows"] == second_info["rows"]
    assert (
        hashlib.sha256(first.read_bytes()).digest()
        == hashlib.sha256(second.read_bytes()).digest()
    )


def test_ingestion_marks_sub_target_workload_unavailable(tmp_path):
    workload = tmp_path / "small.arrow"
    write_synthetic_arrow(workload, target_bytes=1_000_000)

    result = benchmark_ingestion(workload)

    assert result.status == "unavailable"
    assert result.observed is None
    assert result.target_met is None
    assert "required" in result.details["reason"]


def test_small_ingestion_measurement_is_real_when_size_gate_is_lowered(tmp_path):
    workload = tmp_path / "small.arrow"
    write_synthetic_arrow(workload, target_bytes=1_000_000)

    result = benchmark_ingestion(workload, minimum_bytes=1)

    assert result.status in {"passed", "failed"}
    assert result.observed is not None
    assert result.details["rows"] > 0
    assert result.details["available_messages"]


def test_diagnostic_and_memory_metrics_are_measured_or_explicitly_unavailable(tmp_path):
    workload = tmp_path / "small.arrow"
    write_synthetic_arrow(workload, target_bytes=1_000_000)

    results = (
        benchmark_diagnostic(workload, minimum_bytes=1),
        benchmark_memory(workload, minimum_bytes=1),
    )

    for result in results:
        assert result.status in {"passed", "failed", "unavailable"}
        if result.status != "unavailable":
            assert result.observed is not None
            assert result.target_met in {True, False}

    diagnostic = results[0]
    if diagnostic.status != "unavailable":
        assert diagnostic.details["measurement_semantics"] == (
            "steady_state_after_preload_and_warmup"
        )
        assert diagnostic.details["target_scope"] == (
            "steady-state only; cold-start is reported separately"
        )
        assert diagnostic.details["preload"]["completed"] is True
        assert diagnostic.details["preload"]["modules"] == list(DIAGNOSTIC_MODULES)
        assert diagnostic.details["warmup"]["completed"] is True
        assert diagnostic.details["cold_start"]["status"] in {
            "measured",
            "unavailable",
        }
        if diagnostic.details["cold_start"]["status"] == "measured":
            assert diagnostic.details["cold_start"]["observed_ms"] > 0
            assert diagnostic.details["cold_start"]["target_met"] in {True, False}
            assert (
                "fresh child process cold import"
                in diagnostic.details["cold_start"]["scope"]
            )


def test_batch_benchmark_reports_a_measured_value():
    result = benchmark_batch(cases=2, workers=2)

    assert result.status in {"passed", "failed", "unavailable"}
    if result.status != "unavailable":
        assert result.observed is not None
        assert result.details == {
            "cases": 2,
            "workers": 2,
            "elapsed_s": result.details["elapsed_s"],
        }


def test_sitl_default_uses_a_real_local_fallback_when_docker_is_absent():
    result = benchmark_sitl()

    assert result.status in {"passed", "failed"}
    assert result.observed is not None
    assert result.target_met in {True, False}
    assert result.details["runner"] in {"local_headless", "native_sim_vehicle"}
    assert result.details["scenarios"] == 3


def test_sitl_docker_absence_is_recorded_without_dry_run_throughput(monkeypatch):
    monkeypatch.setattr("benchmarks.acceptance.shutil.which", lambda _: None)

    result = benchmark_sitl(execute=True)

    assert result.status in {"passed", "failed"}
    assert result.observed is not None
    assert result.details["runner"] in {"local_headless", "native_sim_vehicle"}
    assert "fallback_reason" in result.details
    assert result.details["commands"]
    assert all(result_item[0] != "docker" for result_item in result.details["commands"])


def test_environment_report_contains_reproduction_fields():
    environment = environment_snapshot()

    assert environment["python"]
    assert environment["platform"]
    assert "cpu_count" in environment
    assert "package_versions" in environment
    assert set(TARGETS) == {
        "ingestion_latency_ms",
        "diagnostic_latency_ms",
        "peak_memory_mb",
        "batch_throughput_logs_s",
        "sitl_throughput_logs_h",
    }


def test_literal_benchmark_script_entry_resolves_local_imports():
    script = Path(__file__).parents[2] / "benchmarks" / "acceptance.py"
    completed = subprocess.run(
        [sys.executable, str(script), "--help"],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert completed.returncode == 0
    assert "usage:" in completed.stdout.lower()
