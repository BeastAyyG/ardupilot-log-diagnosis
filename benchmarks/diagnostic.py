"""Cold and steady-state timing for the implemented diagnostic path."""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

if __package__:
    from .support import (
        TARGET_BYTES,
        TARGETS,
        BenchmarkResult,
        BenchmarkUnavailable,
        require_arrow_input,
        threshold_result,
        unavailable,
    )
else:  # pragma: no cover - exercised when imported by the script entry point
    _PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
    if _PROJECT_ROOT not in sys.path:
        sys.path.insert(0, _PROJECT_ROOT)
    from benchmarks.support import (
        TARGET_BYTES,
        TARGETS,
        BenchmarkResult,
        BenchmarkUnavailable,
        require_arrow_input,
        threshold_result,
        unavailable,
    )

DIAGNOSTIC_MODULES = (
    "src.core.ingestion.arrow_parser",
    "src.core.causality.cita_dag",
    "src.core.causality.impact_boundary",
    "src.core.dynamics.welch_fft",
    "src.core.physics.rigid_body_6dof",
    "src.core.remediation.safety_clamper",
)


def _axis(table: Any, name: str) -> Any:
    if table is None or name not in table.column_names:
        raise BenchmarkUnavailable(f"required telemetry column is absent: {name}")
    try:
        return table[name].combine_chunks().to_numpy(zero_copy_only=False)
    except (TypeError, ValueError, RuntimeError) as exc:
        raise BenchmarkUnavailable(f"telemetry column {name} is not numeric") from exc


def diagnostic_case(signal: Any, *, sample_rate_hz: float = 400.0) -> dict[str, Any]:
    """Run the implemented physics, causal, dynamics, and remediation path."""

    import numpy as np

    from src.core.causality.cita_dag import build_cita_dag
    from src.core.causality.impact_boundary import detect_impact_boundary
    from src.core.dynamics.welch_fft import extract_welch_psd
    from src.core.physics.rigid_body_6dof import solve_rigid_body_6dof
    from src.core.remediation.safety_clamper import clamp_parameter_changes

    samples = np.ascontiguousarray(np.asarray(signal, dtype=np.float64)[:8192])
    if samples.size < 64 or not np.isfinite(samples).all():
        raise BenchmarkUnavailable("VIBE/VibeZ requires at least 64 finite samples")
    times_us = np.arange(samples.size, dtype=np.float64) * (
        1_000_000.0 / sample_rate_hz
    )
    acceleration = np.zeros((samples.size, 3), dtype=np.float64)
    acceleration[:, 2] = 9.80665
    velocity = np.zeros_like(acceleration)
    velocity[:, 0] = 20.0
    acceleration[-1, 2] = 40.0 * 9.80665
    velocity[-1, 0] = 0.0
    zeros = np.zeros_like(acceleration)
    residual = solve_rigid_body_6dof(
        acceleration,
        zeros,
        zeros,
        zeros,
        mass_kg=1.0,
        inertia_kg_m2=np.eye(3),
        gravity_body=[0.0, 0.0, 9.80665],
    )
    impact = detect_impact_boundary(times_us, acceleration, velocity)
    events = {
        "power": {"onset_us": float(times_us[samples.size // 3]), "score": 0.9},
        "propulsion": {
            "onset_us": float(times_us[samples.size // 2]),
            "score": float(np.max(np.abs(samples))),
        },
        "impact": {"onset_us": float(times_us[-1]), "score": 1.0},
    }
    dag = build_cita_dag(
        events,
        dependencies=[("power", "propulsion"), ("propulsion", "impact")],
        impact_boundary_us=float(times_us[-1]),
    )
    spectrum = extract_welch_psd(
        samples, sample_rate_hz, nperseg=min(1024, samples.size)
    )
    changes = clamp_parameter_changes(
        {"INS_HNTCH_FREQ": 180.0},
        {"INS_HNTCH_FREQ": spectrum.ins_hntch_freq or 180.0},
    )
    return {
        "force_residual_max": float(np.max(residual.force_norm)),
        "impact": impact.as_dict(),
        "causal_chain": dag.as_dict(),
        "notch_parameters": spectrum.parameters,
        "param_diff": changes.as_dict(),
    }


def _preload_modules() -> dict[str, Any]:
    start = time.perf_counter()
    imported: list[str] = []
    try:
        for module_name in DIAGNOSTIC_MODULES:
            importlib.import_module(module_name)
            imported.append(module_name)
    except ImportError as exc:
        raise BenchmarkUnavailable(f"diagnostic preload requires {exc.name}") from exc
    return {
        "completed": True,
        "modules": imported,
        "elapsed_ms": (time.perf_counter() - start) * 1000.0,
    }


def _cold_observation(path: Path) -> dict[str, Any]:
    wall_start = time.perf_counter()
    try:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "benchmarks.acceptance",
                "--diagnostic-child",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "status": "unavailable",
            "reason": f"cold process could not start: {exc}",
        }
    process_elapsed_ms = (time.perf_counter() - wall_start) * 1000.0
    if completed.returncode != 0:
        return {
            "status": "unavailable",
            "reason": "cold diagnostic process failed",
            "stderr": completed.stderr[-500:],
        }
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return {"status": "unavailable", "reason": f"invalid cold evidence: {exc}"}
    if result.get("status") != "measured":
        return result
    result["process_elapsed_ms"] = process_elapsed_ms
    result["target_met"] = process_elapsed_ms < TARGETS["diagnostic_latency_ms"]["value"]
    return result


def benchmark_diagnostic(
    path: str | Path, *, minimum_bytes: int = TARGET_BYTES
) -> BenchmarkResult:
    """Measure steady-state parse plus diagnosis and retain cold-start evidence."""

    try:
        file_path = require_arrow_input(path, minimum_bytes=minimum_bytes)
        preload = _preload_modules()
        import numpy as np

        from src.core.ingestion.arrow_parser import parse_arrow
    except (BenchmarkUnavailable, ImportError) as exc:
        return unavailable("diagnostic_latency_ms", str(exc))

    warmup_start = time.perf_counter()
    try:
        diagnostic_case(0.5 * np.sin(np.arange(8192, dtype=np.float64) / 18.0))
    except BenchmarkUnavailable as exc:
        return unavailable("diagnostic_latency_ms", str(exc))
    warmup = {
        "completed": True,
        "elapsed_ms": (time.perf_counter() - warmup_start) * 1000.0,
        "samples": 8192,
    }
    cold = _cold_observation(file_path)
    start = time.perf_counter()
    parsed = parse_arrow(file_path)
    try:
        evidence = diagnostic_case(_axis(parsed.table("VIBE"), "VibeZ"))
    except BenchmarkUnavailable as exc:
        return unavailable(
            "diagnostic_latency_ms", str(exc), input_bytes=file_path.stat().st_size
        )
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    return threshold_result(
        "diagnostic_latency_ms",
        elapsed_ms,
        input_bytes=file_path.stat().st_size,
        evidence=evidence,
        measurement_semantics="steady_state_after_preload_and_warmup",
        target_scope="steady-state only; cold-start is reported separately",
        preload=preload,
        warmup=warmup,
        cold_start=cold,
    )


def diagnostic_cold_child(path: str | Path) -> dict[str, Any]:
    """Measure a fresh child process before any diagnostic module preload."""

    import_start = time.perf_counter()
    file_path = require_arrow_input(path, minimum_bytes=1)
    from src.core.ingestion.arrow_parser import parse_arrow

    parsed = parse_arrow(file_path, ("VIBE",))
    evidence = diagnostic_case(_axis(parsed.table("VIBE"), "VibeZ"))
    return {
        "status": "measured",
        "observed_ms": (time.perf_counter() - import_start) * 1000.0,
        "scope": "fresh child process cold import plus parse and diagnosis",
        "evidence": evidence,
    }
