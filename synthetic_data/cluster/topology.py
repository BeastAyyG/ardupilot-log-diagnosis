"""Laptop-to-DGX topology probing and preflight for the cluster runtime.

The prober reports only what it can verify on the current host; every field
that cannot be checked here is reported as an explicit failure reason rather
than assumed. Nothing in this module executes flights.
"""

from __future__ import annotations

import hashlib
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

PROBE_SCHEMA = "logdiagnosis.cluster-host-probe/v1"
SUPPORTED_PROFILES = ("laptop", "dgx")


def _unshare_support(unshare_path: str | None) -> dict[str, Any]:
    """Probe unprivileged user+network namespace support via `unshare -Urn`."""

    if unshare_path is None:
        return {
            "unshare_binary": None,
            "user_network_namespace_ok": False,
            "reason": "util-linux 'unshare' not found on PATH",
        }
    digest = hashlib.sha256(Path(unshare_path).read_bytes()).hexdigest()
    try:
        result = subprocess.run(
            [unshare_path, "-Urn", "true"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "unshare_binary": unshare_path,
            "unshare_sha256": digest,
            "user_network_namespace_ok": False,
            "reason": f"probe failed to execute: {exc}",
        }
    if result.returncode == 0:
        return {
            "unshare_binary": unshare_path,
            "unshare_sha256": digest,
            "user_network_namespace_ok": True,
            "reason": "unshare -Urn true succeeded",
        }
    stderr = result.stderr.decode(errors="replace").strip()
    return {
        "unshare_binary": unshare_path,
        "unshare_sha256": digest,
        "user_network_namespace_ok": False,
        "reason": f"unshare -Urn exited {result.returncode}: {stderr[:200]}",
    }


def _capacity() -> dict[str, Any]:
    cpu = os_cpu_count()
    mem = mem_total_gb()
    return {"cpu_count": cpu, "mem_total_gb": mem}


def os_cpu_count() -> int:
    import os

    return os.cpu_count() or 0


def mem_total_gb() -> float | None:
    try:
        import psutil  # type: ignore[import-not-found]

        return round(psutil.virtual_memory().total / 1024**3, 2)
    except Exception:  # noqa: BLE001 - optional dependency
        pass
    try:
        # /proc/meminfo on Linux
        text = Path("/proc/meminfo").read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.startswith("MemTotal:"):
                kb = float(line.split()[1])
                return round(kb / 1024**2, 2)
    except OSError:
        pass
    return None


def probe_host(
    *,
    check_namespaces: bool = True,
    min_cpu: int = 2,
    min_mem_gb: float = 4.0,
) -> dict[str, Any]:
    """Snapshot host capability with explicit fail reasons, never guesses."""

    system = platform.system()
    machine = platform.machine()
    unshare_path = shutil.which("unshare") if system != "Windows" else None
    probe: dict[str, Any] = {
        "schema": PROBE_SCHEMA,
        "system": system,
        "machine": machine,
        "python_version": platform.python_version(),
        **_capacity(),
        "arch_supported": machine.lower() in {"amd64", "x86_64", "arm64", "aarch64"},
    }
    if check_namespaces and system == "Linux":
        probe.update(_unshare_support(unshare_path))
    else:
        probe.update(
            {
                "unshare_binary": None,
                "user_network_namespace_ok": False,
                "reason": (
                    "namespace isolation requires Linux; run inside WSL2 or "
                    "the ARM64 container on DGX"
                ),
            }
        )
    cpu_ok = probe["cpu_count"] >= min_cpu
    mem_ok = probe["mem_total_gb"] is None or probe["mem_total_gb"] >= min_mem_gb
    probe["capacity_ok"] = bool(cpu_ok and mem_ok)
    if not cpu_ok:
        probe["capacity_reason"] = f"requires >= {min_cpu} CPUs"
    elif not mem_ok:
        probe["capacity_reason"] = f"requires >= {min_mem_gb} GiB RAM"
    else:
        probe["capacity_reason"] = "ok"
    return probe


def recommend_topology(probe: dict[str, Any], *, profile: str) -> dict[str, Any]:
    """Map a host probe onto lane counts, image, and storage guidance."""

    if profile not in SUPPORTED_PROFILES:
        raise ValueError(f"unknown profile: {profile}; expected {SUPPORTED_PROFILES}")
    if profile == "dgx":
        lanes = max(1, min(32, int(probe.get("cpu_count", 0) // 2)))
        storage_root = "/data/sitl-experiments"
        image = "ghcr.io/<org>/ardupilot-sitl-copter:<pinned-tag>@sha256:<digest>"
        requires_container = True
    else:
        lanes = max(1, min(4, int(probe.get("cpu_count", 1) // 2)))
        storage_root = str(Path.home() / "sitl-experiments")
        image = None
        requires_container = False
    return {
        "profile": profile,
        "recommended_max_concurrent": lanes,
        "storage_root": storage_root,
        "container_image": image,
        "requires_container": requires_container,
        "sequential_fallback_lanes": 1,
        "notes": [
            "Pairs must land in one batch so lineage metadata stays adjacent.",
            "Namespace-isolated lanes may run concurrently; ports are "
            "disjoint per slot and recycled only across waves.",
            "Without verified user/network namespaces, fall back to lanes=1.",
        ],
    }
