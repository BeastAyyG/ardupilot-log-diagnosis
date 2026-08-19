"""Safe input-format detection for flight-log tooling."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
from typing import Any


class FileFormatError(ValueError):
    """Raised when a path cannot be inspected safely."""


_FORMAT_NAMES = {
    "ardupilot_bin": "ArduPilot DataFlash (.bin)",
    "px4_ulog": "PX4 ULog (.ulg)",
    "mavlink_tlog": "MAVLink telemetry log (.tlog)",
    "text_log": "ArduPilot DataFlash text log (.log)",
    "betaflight_bbl": "Betaflight Blackbox (.bbl/.bfl)",
    "unknown": "Unknown flight-log format",
}

_FORMAT_DEPENDENCIES = {
    "ardupilot_bin": "pymavlink",
    "text_log": "pymavlink",
    "px4_ulog": "pyulog",
    "mavlink_tlog": "pymavlink",
    "betaflight_bbl": "orangebox",
}


def supported_format_kinds() -> list[str]:
    """Return input formats whose parser dependency is available at runtime."""
    return [
        kind
        for kind, dependency in _FORMAT_DEPENDENCIES.items()
        if importlib.util.find_spec(dependency) is not None
    ]


def detect_file_format(path: str | Path, *, hash_file: bool = False) -> dict[str, Any]:
    """Return a format/capability description without parsing the full file.

    Magic bytes are authoritative where available; the suffix is retained as a
    hint only. supported deliberately means supported by this project.
    """

    file_path = Path(path)
    if not file_path.exists():
        raise FileFormatError(f"Input file does not exist: {file_path}")
    if not file_path.is_file():
        raise FileFormatError(f"Input path is not a regular file: {file_path}")

    stat = file_path.stat()
    with file_path.open("rb") as handle:
        prefix = handle.read(16)

    suffix = file_path.suffix.lower()
    if prefix.startswith(b"\xa3\x95"):
        kind = "ardupilot_bin"
    elif prefix.startswith(b"ULog") or prefix.startswith(b"\x55\x4c\x6f\x67"):
        kind = "px4_ulog"
    elif suffix == ".tlog":
        kind = "mavlink_tlog"
    elif suffix == ".log" and not prefix.startswith(b"\xa3\x95"):
        kind = "text_log"
    elif suffix in {".bbl", ".bfl"} or (prefix.startswith(b"H Product:") and b"Blackbox" in prefix):
        kind = "betaflight_bbl"
    else:
        kind = "unknown"

    px4_available = importlib.util.find_spec("pyulog") is not None
    tlog_available = importlib.util.find_spec("pymavlink") is not None
    parser_name = {"ardupilot_bin": "pymavlink.DFReader_binary", "text_log": "pymavlink.DFReader_text", "px4_ulog": "pyulog.ULog", "mavlink_tlog": "pymavlink.mavutil.mavlink_connection", "betaflight_bbl": "orangebox.Parser"}.get(kind)
    supported = ((kind in {"ardupilot_bin", "text_log"} and tlog_available) or (kind == "px4_ulog" and px4_available) or (kind == "mavlink_tlog" and tlog_available))
    blackbox_available = importlib.util.find_spec("orangebox") is not None
    supported = supported or (kind == "betaflight_bbl" and blackbox_available)
    result: dict[str, Any] = {
        "path": str(file_path),
        "filename": file_path.name,
        "extension": suffix,
        "format": kind,
        "format_name": _FORMAT_NAMES[kind],
        "size_bytes": stat.st_size,
        "modified_ns": stat.st_mtime_ns,
        "supported": supported,
        "parser": parser_name,
        "adapter_dependency": _FORMAT_DEPENDENCIES.get(kind),
        "adapter_available": bool(supported),
        "capabilities": ["generic_telemetry_checks"] if kind in {"px4_ulog", "mavlink_tlog"} and supported else ["all_ardupilot_checks"] if kind in {"ardupilot_bin", "text_log"} and supported else ["betaflight_tuning", "generic_telemetry_checks"] if kind == "betaflight_bbl" and supported else [],
    }
    if kind == "unknown":
        result["unsupported_reason"] = "The file signature and extension do not identify a supported flight-log format."
    elif not supported:
        dependency = _FORMAT_DEPENDENCIES.get(kind)
        result["unsupported_reason"] = (
            f"Install the '{dependency}' parser dependency to enable this format."
            if dependency
            else "No compatible parser is available for this format."
        )
    if hash_file:
        digest = hashlib.sha256()
        with file_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        result["sha256"] = digest.hexdigest()
    return result
