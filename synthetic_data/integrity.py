"""Bounded JSON and contained-path helpers for experiment artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

MAX_JSON_BYTES = 20 * 1024 * 1024


class VerificationError(ValueError):
    """A run failed an integrity or causal-observability gate."""


def read_json(path: Path, *, maximum_bytes: int = MAX_JSON_BYTES) -> dict[str, Any]:
    if not path.is_file():
        raise VerificationError(f"required JSON file is missing: {path.name}")
    if path.stat().st_size > maximum_bytes:
        raise VerificationError(f"JSON file exceeds the size limit: {path.name}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerificationError(f"invalid JSON file: {path.name}") from exc
    if not isinstance(value, dict):
        raise VerificationError(f"JSON root must be an object: {path.name}")
    return value


def safe_child(directory: Path, filename: object, expected_suffix: str) -> Path:
    name = str(filename or "")
    candidate = Path(name)
    if (
        not name
        or candidate.is_absolute()
        or candidate.name != name
        or candidate.suffix.lower() != expected_suffix.lower()
    ):
        raise VerificationError(f"unsafe experiment artifact name: {name}")
    resolved_directory = directory.resolve()
    resolved = (resolved_directory / candidate).resolve()
    if resolved.parent != resolved_directory:
        raise VerificationError(f"artifact escapes its experiment directory: {name}")
    return resolved


def atomic_json(path: Path, value: object) -> None:
    text = json.dumps(value, indent=2, sort_keys=True) + "\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)
