"""Safe, read-only directory indexing for flight logs.

This covers the useful offline part of the official WebTools Log Finder: find
logs, identify their adapters, group them by a conservative configuration key,
and expose parameter-change context without uploading or mutating anything.
"""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from src.parser.bin_parser import LogParser
from src.parser.file_format import detect_file_format


LOG_SUFFIXES = frozenset({".bin", ".log", ".ulg", ".ulog", ".tlog", ".bbl", ".bfl"})


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hardware_id(parameters: dict[str, Any], metadata: dict[str, Any]) -> str | None:
    for name in ("BRD_SERIAL_NUM", "BRD_SERIALNUMBER", "SERIAL_NUMBER", "SERIAL_NUM", "INS_SERIALNO"):
        value = parameters.get(name)
        if value not in (None, "", 0, 0.0):
            return f"{name}:{value}"
    value = metadata.get("hardware_id")
    if value not in (None, "", "Unknown"):
        return str(value)
    return None


def _configuration_key(metadata: dict[str, Any], parameters: dict[str, Any] | None = None) -> str:
    vehicle = str(metadata.get("vehicle_type", "Unknown"))
    board = str(metadata.get("board", "Unknown"))
    firmware = str(metadata.get("firmware_version", "Unknown"))
    hardware_id = _hardware_id(parameters or {}, metadata)
    return "|".join((hardware_id or "hardware:unknown", vehicle, board, firmware))


def find_logs(
    root: str | Path,
    *,
    recursive: bool = True,
    parse_metadata: bool = True,
    hash_files: bool = False,
    include_unsupported: bool = False,
    max_files: int = 10_000,
) -> dict[str, Any]:
    """Index supported flight-log files below ``root`` without writing files.

    ``root`` must be an existing directory.  A bounded ``max_files`` prevents
    accidental scans of an unexpectedly large mounted drive.  Unsupported
    optional adapters are retained with their detected reason when requested.
    """
    root_path = Path(root).expanduser()
    if not root_path.exists():
        raise ValueError(f"Log index root does not exist: {root_path}")
    if not root_path.is_dir():
        raise ValueError(f"Log index root is not a directory: {root_path}")
    try:
        max_files = int(max_files)
    except (TypeError, ValueError) as exc:
        raise ValueError("max_files must be an integer") from exc
    if max_files < 1 or max_files > 100_000:
        raise ValueError("max_files must be between 1 and 100000")

    iterator = root_path.rglob("*") if recursive else root_path.glob("*")
    candidates = sorted((path for path in iterator if path.is_file() and path.suffix.lower() in LOG_SUFFIXES), key=lambda path: str(path).lower())
    candidate_count = len(candidates)
    truncated = candidate_count > max_files
    candidates = candidates[:max_files]

    entries: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    previous_parameters: dict[str, dict[str, Any]] = {}
    for path in candidates:
        try:
            detected = detect_file_format(path, hash_file=hash_files)
            if not detected.get("supported", False) and not include_unsupported:
                continue
            item: dict[str, Any] = {
                "path": str(path),
                "relative_path": str(path.relative_to(root_path)),
                "filename": path.name,
                "modified_ns": path.stat().st_mtime_ns,
                "size_bytes": path.stat().st_size,
                "format": detected,
                "status": "reliable" if detected.get("supported", False) else "unsupported_optional",
            }
            if parse_metadata and detected.get("supported", False):
                parsed = LogParser(str(path)).parse()
                metadata = parsed.get("metadata", {}) or {}
                parameters = parsed.get("parameters", {}) or {}
                configuration_key = _configuration_key(metadata, parameters)
                previous = previous_parameters.get(configuration_key)
                changed_from_previous = sorted(
                    name for name in set(parameters) | set(previous or {})
                    if (previous or {}).get(name) != parameters.get(name)
                ) if previous is not None else []
                previous_parameters[configuration_key] = dict(parameters)
                item.update({
                    "metadata": {
                        "vehicle_type": metadata.get("vehicle_type", "Unknown"),
                        "firmware_version": metadata.get("firmware_version", "Unknown"),
                        "firmware_hash": metadata.get("firmware_hash", "Unknown"),
                        "board": metadata.get("board", "Unknown"),
                        "hardware_id": _hardware_id(parameters, metadata),
                        "duration_sec": metadata.get("duration_sec", 0.0),
                        "total_messages": metadata.get("total_messages", 0),
                    },
                    "configuration_key": configuration_key,
                    "parameter_count": len(parameters),
                    "parameter_change_count": len(parsed.get("parameter_changes", []) or []),
                    "changed_from_previous": changed_from_previous,
                    "parameter_comparison": "compared" if previous is not None else "baseline",
                    "parse_quality": (metadata.get("quality_report", {}) or {}).get("overall_status", "UNKNOWN"),
                })
            if hash_files and "sha256" not in item["format"]:
                item["sha256"] = _sha256(path)
            entries.append(item)
        except Exception as exc:  # one corrupt file must not abort the directory scan
            errors.append({"path": str(path), "error": str(exc)})

    entries.sort(key=lambda item: (str(item.get("configuration_key", "Unknown")), int(item.get("modified_ns", 0)), str(item.get("path", "")).lower()))
    groups: dict[str, list[str]] = defaultdict(list)
    for item in entries:
        groups[str(item.get("configuration_key", "Unknown"))].append(item["relative_path"])
    return {
        "schema_version": "log-index.v1",
        "status": "reliable" if entries else "insufficient_data",
        "root": str(root_path),
        "recursive": recursive,
        "parse_metadata": parse_metadata,
        "hash_files": hash_files,
        "entry_count": len(entries),
        "candidate_count": candidate_count,
        "scanned_candidates": len(candidates),
        "truncated": truncated,
        "format_counts": dict(sorted(Counter(str(item["format"].get("format", "unknown")) for item in entries).items())),
        "configuration_groups": dict(sorted(groups.items())),
        "entries": entries,
        "errors": errors,
        "read_only": True,
    }
