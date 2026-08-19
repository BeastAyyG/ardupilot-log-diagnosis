"""Honest, local acceptance benchmarks for the CITA-Nexus work order.

The module measures only work that is present in this checkout. A missing
optional dependency, Docker runtime, or required telemetry field is reported
as unavailable; it is never converted into a passing synthetic result.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

if __package__:
    from .diagnostic import (
        benchmark_diagnostic,
        diagnostic_case,
        diagnostic_cold_child,
    )
    from .support import (
        TARGET_BYTES,
        TARGETS,
        BenchmarkResult,
        BenchmarkUnavailable,
        environment_snapshot,
        require_arrow_input,
        threshold_result,
        unavailable,
        write_synthetic_arrow,
    )
else:  # pragma: no cover - exercised by the literal script entry point
    _PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
    if _PROJECT_ROOT not in sys.path:
        sys.path.insert(0, _PROJECT_ROOT)
    from benchmarks.diagnostic import (
        benchmark_diagnostic,
        diagnostic_case,
        diagnostic_cold_child,
    )
    from benchmarks.support import (
        TARGET_BYTES,
        TARGETS,
        BenchmarkResult,
        BenchmarkUnavailable,
        environment_snapshot,
        require_arrow_input,
        threshold_result,
        unavailable,
        write_synthetic_arrow,
    )


def benchmark_ingestion(
    path: str | Path, *, minimum_bytes: int = TARGET_BYTES
) -> BenchmarkResult:
    """Measure the existing Arrow parser against a verified file size."""

    try:
        file_path = require_arrow_input(path, minimum_bytes=minimum_bytes)
        from src.core.ingestion.arrow_parser import DEFAULT_MESSAGES, parse_arrow
    except (BenchmarkUnavailable, ImportError) as exc:
        return unavailable("ingestion_latency_ms", str(exc))
    start = time.perf_counter()
    result = parse_arrow(file_path, DEFAULT_MESSAGES)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    return threshold_result(
        "ingestion_latency_ms",
        elapsed_ms,
        input_bytes=file_path.stat().st_size,
        rows=result.total_rows,
        record_batches=result.record_batches,
        available_messages=result.available_messages,
    )


def _memory_snapshot() -> int | None:
    """Return a platform peak working-set value when the OS exposes one."""

    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class Counters(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("page_faults", wintypes.DWORD),
                    ("peak_ws", ctypes.c_size_t),
                    ("ws", ctypes.c_size_t),
                    ("peak_paged_pool", ctypes.c_size_t),
                    ("paged_pool", ctypes.c_size_t),
                    ("peak_nonpaged_pool", ctypes.c_size_t),
                    ("nonpaged_pool", ctypes.c_size_t),
                    ("peak_pagefile", ctypes.c_size_t),
                    ("pagefile", ctypes.c_size_t),
                    ("private_usage", ctypes.c_size_t),
                ]

            counters = Counters()
            counters.cb = ctypes.sizeof(counters)
            psapi = ctypes.WinDLL("psapi", use_last_error=True)
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            function = psapi.GetProcessMemoryInfo
            function.argtypes = [
                wintypes.HANDLE,
                ctypes.POINTER(Counters),
                wintypes.DWORD,
            ]
            function.restype = wintypes.BOOL
            process = kernel.GetCurrentProcess()
            ok = function(process, ctypes.byref(counters), counters.cb)
            return int(counters.peak_ws) if ok else None
        except (AttributeError, OSError, TypeError):
            return None
    try:
        import resource

        value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        return value * (1024 if sys.platform != "darwin" else 1)
    except (ImportError, AttributeError, OSError):
        return None


def benchmark_memory(
    path: str | Path, *, minimum_bytes: int = TARGET_BYTES
) -> BenchmarkResult:
    """Measure a fresh child process peak working set while parsing the workload."""

    try:
        file_path = require_arrow_input(path, minimum_bytes=minimum_bytes)
    except (BenchmarkUnavailable, ImportError) as exc:
        return unavailable("peak_memory_mb", str(exc))
    try:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "benchmarks.acceptance",
                "--memory-child",
                str(file_path),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return unavailable(
            "peak_memory_mb", f"fresh memory process could not start: {exc}"
        )
    if completed.returncode != 0:
        return unavailable(
            "peak_memory_mb",
            "fresh memory process failed",
            stderr=completed.stderr[-500:],
        )
    try:
        evidence = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return unavailable(
            "peak_memory_mb", f"fresh memory process returned invalid evidence: {exc}"
        )
    if evidence.get("status") != "measured":
        return unavailable(
            "peak_memory_mb",
            str(evidence.get("reason", "peak working-set sampling failed")),
        )
    return threshold_result("peak_memory_mb", float(evidence["peak_mb"]), **evidence)


def _measure_memory_child(path: str | Path) -> dict[str, Any]:
    """Measure only parser startup and parsing in the fresh child process."""

    file_path = require_arrow_input(path, minimum_bytes=1)
    from src.core.ingestion.arrow_parser import parse_arrow

    baseline = _memory_snapshot()
    if baseline is None:
        return {
            "status": "unavailable",
            "reason": "this platform exposes no peak working-set API",
        }
    parse_arrow(file_path)
    peak = _memory_snapshot()
    if peak is None:
        return {"status": "unavailable", "reason": "peak working-set sampling failed"}
    return {
        "status": "measured",
        "baseline_mb": baseline / (1024 * 1024),
        "peak_mb": peak / (1024 * 1024),
        "scope": "fresh child process peak working set",
    }


def benchmark_batch(*, cases: int = 32, workers: int = 14) -> BenchmarkResult:
    """Measure deterministic in-process diagnostic case throughput."""

    if cases < 1 or workers < 1 or workers > 14:
        raise ValueError(
            "cases must be positive and workers must be between one and fourteen"
        )
    try:
        import numpy as np

        from src.core.dynamics.welch_fft import extract_welch_psd
    except ImportError as exc:
        return unavailable("batch_throughput_logs_s", str(exc))
    del extract_welch_psd

    signals = tuple(
        0.5 * np.sin(np.arange(2048, dtype=np.float64) / (18.0 + index % 5))
        for index in range(cases)
    )
    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        tuple(executor.map(diagnostic_case, signals))
    elapsed = time.perf_counter() - start
    throughput = cases / elapsed if elapsed > 0 else float("inf")
    return threshold_result(
        "batch_throughput_logs_s",
        throughput,
        cases=cases,
        workers=workers,
        elapsed_s=elapsed,
    )


def benchmark_sitl(
    *, execute: bool = False, scenarios: Sequence[Mapping[str, Any]] | None = None
) -> BenchmarkResult:
    """Measure Docker SITL explicitly, or the safe local fallback by default."""

    try:
        from src.simulation.sitl_cluster import SITLClusterRunner, SITLScenario
    except ImportError as exc:
        return unavailable("sitl_throughput_logs_h", str(exc))
    if not isinstance(execute, bool):
        raise TypeError("execute must be a bool")
    raw = scenarios or (
        {
            "name": "motor_failure",
            "parameters": {"SIM_ENGINE_FAIL": 1.0},
            "duration_s": 1.0,
        },
        {
            "name": "gps_denial",
            "parameters": {"SIM_GPS_DISABLE": 1.0},
            "duration_s": 1.0,
        },
        {
            "name": "battery_sag",
            "parameters": {"SIM_BATT_VOLTAGE": 10.5},
            "duration_s": 1.0,
        },
    )
    try:
        cases = [
            SITLScenario(
                str(item["name"]),
                dict(item.get("parameters", {})),
                duration_s=float(item.get("duration_s", 1.0)),
            )
            for item in raw
        ]
        docker_available = shutil.which("docker") is not None
        if execute:
            requested_backend = True
        else:
            requested_backend = False
        if execute and docker_available is False:
            fallback_reason = "Docker executable is not available; used local fallback"
        else:
            fallback_reason = None
        start = time.perf_counter()
        results = SITLClusterRunner(
            max_workers=min(14, len(cases)),
            use_docker=requested_backend,
        ).run(cases, dry_run=False, use_docker=requested_backend)
    except (OSError, TypeError, ValueError, ImportError) as exc:
        return unavailable("sitl_throughput_logs_h", f"no SITL fallback can run: {exc}")
    elapsed = time.perf_counter() - start
    failed = [
        result.scenario
        for result in results
        if result.returncode != 0 or result.timed_out
    ]
    if failed:
        return BenchmarkResult(
            "sitl_throughput_logs_h",
            "failed",
            None,
            TARGETS["sitl_throughput_logs_h"]["unit"],
            TARGETS["sitl_throughput_logs_h"],
            False,
            {
                "reason": "one or more SITL scenarios failed",
                "failed_scenarios": failed,
                "elapsed_s": elapsed,
                "runner": sorted({result.runner for result in results}),
            },
        )
    throughput = len(results) / elapsed * 3600.0 if elapsed > 0 else float("inf")
    runner_names = sorted({result.runner for result in results})
    details: dict[str, Any] = {
        "scenarios": len(results),
        "elapsed_s": elapsed,
        "runner": runner_names[0] if len(runner_names) == 1 else runner_names,
        "commands": [list(result.command) for result in results],
    }
    if fallback_reason is not None:
        details["fallback_reason"] = fallback_reason
    return threshold_result(
        "sitl_throughput_logs_h",
        throughput,
        **details,
    )


def run_suite(
    input_path: str | Path | None = None,
    *,
    output_dir: str | Path | None = None,
    batch_cases: int = 32,
    run_sitl: bool = False,
) -> dict[str, Any]:
    """Run all metrics and return a JSON-serializable evidence record."""

    temporary: tempfile.TemporaryDirectory[str] | None = None
    if input_path is None:
        if output_dir is None:
            temporary = tempfile.TemporaryDirectory(prefix="cita-acceptance-")
            input_file = Path(temporary.name) / "synthetic-50mb.arrow"
        else:
            input_file = Path(output_dir) / "synthetic-50mb.arrow"
        workload = write_synthetic_arrow(input_file)
    else:
        input_file = Path(input_path)
        workload = {
            "path": str(input_file),
            "bytes": input_file.stat().st_size if input_file.is_file() else None,
            "synthetic": False,
        }
    results = [
        benchmark_ingestion(input_file),
        benchmark_diagnostic(input_file),
        benchmark_memory(input_file),
        benchmark_batch(cases=batch_cases),
        benchmark_sitl(execute=run_sitl),
    ]
    record = {
        "schema_version": "acceptance-benchmark.v1",
        "environment": environment_snapshot(),
        "workload": workload,
        "targets": TARGETS,
        "results": [item.as_dict() for item in results],
    }
    if temporary is not None:
        temporary.cleanup()
    return record


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        help="existing >=50 MiB Arrow IPC file; otherwise generate deterministic input",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="keep the generated Arrow workload in this directory",
    )
    parser.add_argument("--batch-cases", type=int, default=32)
    parser.add_argument(
        "--run-sitl",
        action="store_true",
        help="explicitly execute Docker SITL; default is unavailable/dry-run",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="return non-zero for unavailable metrics as well as failed targets",
    )
    parser.add_argument("--diagnostic-child", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--memory-child", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.diagnostic_child is not None:
        try:
            evidence = diagnostic_cold_child(args.diagnostic_child)
        except (BenchmarkUnavailable, ImportError) as exc:
            evidence = {"status": "unavailable", "reason": str(exc)}
        print(json.dumps(evidence, sort_keys=True))
        return 0
    if args.memory_child is not None:
        try:
            evidence = _measure_memory_child(args.memory_child)
        except (BenchmarkUnavailable, ImportError) as exc:
            evidence = {"status": "unavailable", "reason": str(exc)}
        print(json.dumps(evidence, sort_keys=True))
        return 0
    record = run_suite(
        args.input,
        output_dir=args.output_dir,
        batch_cases=args.batch_cases,
        run_sitl=args.run_sitl,
    )
    print(json.dumps(record, indent=2, sort_keys=True))
    statuses = {item["status"] for item in record["results"]}
    if "failed" in statuses:
        return 1
    if args.strict and "unavailable" in statuses:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
