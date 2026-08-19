"""Shared acceptance benchmark types, targets, and deterministic workload setup."""

from __future__ import annotations

import math
import os
import platform
import shutil
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

TARGET_BYTES = 50 * 1024 * 1024
TARGETS: dict[str, dict[str, Any]] = {
    "ingestion_latency_ms": {
        "operator": "<=",
        "value": 200.0,
        "unit": "ms",
        "source": "prompt_draft R1",
    },
    "diagnostic_latency_ms": {
        "operator": "<",
        "value": 250.0,
        "unit": "ms",
        "source": "prompt_draft acceptance",
    },
    "peak_memory_mb": {
        "operator": "<",
        "value": 200.0,
        "unit": "MiB",
        "source": "goal-objective",
    },
    "batch_throughput_logs_s": {
        "operator": ">=",
        "value": 30.0,
        "unit": "logs/s",
        "reference_band": "30-45",
        "source": "goal-objective",
    },
    "sitl_throughput_logs_h": {
        "operator": ">=",
        "value": 900.0,
        "unit": "logs/h",
        "reference_band": "900-1000",
        "source": "goal-objective",
    },
}
MESSAGE_NAMES = ("ATT", "VIBE", "RCOU", "BAT", "IMU", "GPS", "POS", "ERR")


class BenchmarkUnavailable(RuntimeError):
    """Raised when a benchmark cannot be measured honestly in this environment."""


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    metric: str
    status: str
    observed: float | None
    unit: str
    target: Mapping[str, Any]
    target_met: bool | None
    details: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def unavailable(metric: str, reason: str, **details: Any) -> BenchmarkResult:
    return BenchmarkResult(
        metric,
        "unavailable",
        None,
        TARGETS[metric]["unit"],
        TARGETS[metric],
        None,
        {"reason": reason, **details},
    )


def threshold_result(metric: str, observed: float, **details: Any) -> BenchmarkResult:
    target = TARGETS[metric]
    operator = target["operator"]
    limit = float(target["value"])
    if operator == "<":
        target_met = observed < limit
    elif operator == "<=":
        target_met = observed <= limit
    elif operator == ">=":
        target_met = observed >= limit
    else:
        raise ValueError(f"unsupported benchmark operator: {operator}")
    return BenchmarkResult(
        metric,
        "passed" if target_met else "failed",
        float(observed),
        target["unit"],
        target,
        target_met,
        details,
    )


def _git_revision() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    revision = completed.stdout.strip()
    return revision if completed.returncode == 0 and revision else None


def environment_snapshot() -> dict[str, Any]:
    """Return the hardware and runtime context needed to reproduce a result."""

    versions: dict[str, str | None] = {}
    try:
        from importlib.metadata import PackageNotFoundError, version

        for package in ("numpy", "scipy", "pyarrow", "pytest", "fastapi", "docker"):
            try:
                versions[package] = version(package)
            except PackageNotFoundError:
                versions[package] = None
    except ImportError:
        versions = {}
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor() or None,
        "cpu_count": os.cpu_count(),
        "docker": shutil.which("docker") is not None,
        "git_revision": _git_revision(),
        "package_versions": versions,
    }


def write_synthetic_arrow(
    path: str | Path, *, target_bytes: int = TARGET_BYTES
) -> dict[str, Any]:
    """Write a deterministic, message-reflectable Arrow IPC workload."""

    if target_bytes < 4096:
        raise ValueError("target_bytes must be at least 4096")
    try:
        import numpy as np
        import pyarrow as pa
        from pyarrow import ipc
    except ImportError as exc:
        raise BenchmarkUnavailable(
            f"synthetic Arrow input requires {exc.name}"
        ) from exc

    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    rows = max(100_000, math.ceil(target_bytes / 56))
    while True:
        index = np.arange(rows, dtype=np.int64)
        phase = index.astype(np.float64) / 400.0
        message_type = np.take(np.asarray(MESSAGE_NAMES), index % len(MESSAGE_NAMES))
        table = pa.table(
            {
                "Type": pa.array(message_type),
                "TimeUS": pa.array(1_000_000 + index * 2_500),
                "Roll": pa.array(np.sin(phase * 0.7)),
                "Pitch": pa.array(np.cos(phase * 0.5)),
                "Yaw": pa.array(np.sin(phase * 0.2)),
                "VibeX": pa.array(0.05 * np.sin(phase * 40.0)),
                "VibeY": pa.array(0.05 * np.sin(phase * 50.0)),
                "VibeZ": pa.array(
                    0.50 * np.sin(phase * 180.0) + 0.01 * np.cos(phase * 7.0)
                ),
            }
        )
        with (
            pa.OSFile(str(file_path), "wb") as sink,
            ipc.new_file(sink, table.schema) as writer,
        ):
            writer.write_table(table)
        size = file_path.stat().st_size
        if size >= target_bytes:
            return {
                "path": str(file_path),
                "bytes": size,
                "rows": rows,
                "synthetic": True,
                "messages": MESSAGE_NAMES,
            }
        rows = math.ceil(rows * target_bytes / max(size, 1) * 1.05)


def require_arrow_input(path: str | Path, *, minimum_bytes: int = TARGET_BYTES) -> Path:
    file_path = Path(path)
    if not file_path.is_file():
        raise BenchmarkUnavailable(f"input file is unavailable: {file_path}")
    size = file_path.stat().st_size
    if size < minimum_bytes:
        raise BenchmarkUnavailable(
            f"input is {size} bytes; a {minimum_bytes}-byte workload is required"
        )
    return file_path
