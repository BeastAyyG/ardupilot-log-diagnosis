"""Exact runtime, source, command, and parameter identities for direct SITL."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import struct
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

SUPPORTED_PYMAVLINK_VERSION = "2.4.49"


def float32_equal(left: object, right: object) -> bool:
    """Compare values exactly as MAVLink PARAM_VALUE float32 payloads."""

    try:
        return struct.pack("!f", float(left)) == struct.pack("!f", float(right))
    except (OverflowError, TypeError, ValueError, struct.error):
        return False


def command_sha256(command: list[str]) -> str:
    payload = json.dumps(command, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def source_snapshot_sha256(
    revision: str, tree: str, submodule_state_sha256: str
) -> str:
    return hashlib.sha256(
        json.dumps(
            {
                "revision": revision,
                "tree": tree,
                "submodule_state_sha256": submodule_state_sha256,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def direct_sitl_command(
    *,
    binary_path: str | Path,
    parameter_file: str | Path,
    plan: Mapping[str, Any],
    instance: int,
    endpoint_ip: str,
    mavlink_port: int,
) -> list[str]:
    frame_models = {"quad": "+", "hexa": "hexa", "octa": "octa"}
    model = frame_models.get(str(plan.get("frame", "")))
    if model is None:
        raise ValueError("run plan has an unsupported direct SITL frame")
    if endpoint_ip != "127.0.0.1":
        raise ValueError(
            "direct SITL runs are loopback-only; endpoint_ip must be 127.0.0.1"
        )
    home = plan.get("fixed_home", {})
    custom_location = ",".join(
        str(float(home[name]))
        for name in ("latitude", "longitude", "altitude_m", "heading_deg")
    )
    start_time = plan.get("simulation_start_unix_sec")
    if isinstance(start_time, bool) or not isinstance(start_time, int):
        raise ValueError("run plan lacks an integer simulation_start_unix_sec")
    port_offset = 10 * int(instance)
    return [
        str(Path(binary_path).resolve()),
        "--vehicle",
        "ArduCopter",
        "-w",
        "--model",
        model,
        "--speedup",
        "1",
        "--defaults",
        str(Path(parameter_file).resolve()),
        "--home",
        custom_location,
        "--start-time",
        str(start_time),
        "--sysid",
        str(int(instance) + 1),
        "--base-port",
        str(5760 + port_offset),
        "--rc-in-port",
        "0",
        "--sim-address",
        endpoint_ip,
        "--sim-port-in",
        str(9003 + port_offset),
        "--sim-port-out",
        str(9002 + port_offset),
        "--irlock-port",
        str(9005 + port_offset),
        "--instance",
        str(instance),
        "--serial0",
        f"tcpclient:{endpoint_ip}:{mavlink_port}",
        "--serial1",
        "none",
        "--serial2",
        "none",
        "--serial5",
        "none",
        "--serial6",
        "none",
        "--serial7",
        "none",
        "--serial8",
        "none",
    ]


def runtime_identity(*, enforce_supported_pymavlink: bool) -> dict[str, str]:
    version = importlib.metadata.version("pymavlink")
    if enforce_supported_pymavlink and version != SUPPORTED_PYMAVLINK_VERSION:
        raise RuntimeError(
            "direct SITL execution requires tested pymavlink "
            f"{SUPPORTED_PYMAVLINK_VERSION}, found {version}"
        )
    return {
        "pymavlink_version": version,
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "system": platform.system(),
        "machine": platform.machine(),
        "executable_sha256": hashlib.sha256(
            Path(sys.executable).read_bytes()
        ).hexdigest(),
    }


def _git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *arguments],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        timeout=30.0,
        check=True,
        text=True,
    ).stdout


def attest_clean_source(root: Path, expected_revision: str) -> dict[str, Any]:
    revision = _git(root, "rev-parse", "HEAD").strip().lower()
    if revision != str(expected_revision).lower():
        raise RuntimeError("ArduPilot checkout HEAD differs from the run plan")
    tracked_status = _git(
        root,
        "status",
        "--porcelain=v1",
        "--untracked-files=no",
        "--ignore-submodules=none",
    ).strip()
    if tracked_status:
        raise RuntimeError("ArduPilot checkout has dirty tracked files or submodules")
    submodules = _git(root, "submodule", "status", "--recursive").splitlines()
    if any(line and line[0] in {"-", "+", "U"} for line in submodules):
        raise RuntimeError("ArduPilot submodule state differs from the pinned commit")
    tree = _git(root, "rev-parse", "HEAD^{tree}").strip().lower()
    normalized_submodules = "\n".join(line.rstrip() for line in submodules)
    submodule_hash = hashlib.sha256(normalized_submodules.encode()).hexdigest()
    snapshot = source_snapshot_sha256(revision, tree, submodule_hash)
    return {
        "source_revision": revision,
        "source_tree_sha1": tree,
        "submodule_state_sha256": submodule_hash,
        "source_snapshot_sha256": snapshot,
        "tracked_source_clean": True,
    }
