"""Extract and export mission/configuration artifacts with hashes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ARTIFACT_MESSAGE_TYPES = ("CMD", "FENCE", "RALLY", "FILE", "ORGN", "HOME", "SCR", "SLOG", "LUA")


def artifact_rows(parsed: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    messages = parsed.get("messages", {}) or {}
    result: dict[str, list[dict[str, Any]]] = {}
    for name in ARTIFACT_MESSAGE_TYPES:
        values = messages.get(name, [])
        if isinstance(values, list) and values:
            result[name] = [item for item in values if isinstance(item, dict)]
    return result


def artifact_manifest(parsed: dict[str, Any]) -> dict[str, Any]:
    entries: dict[str, Any] = {}
    for name, rows in artifact_rows(parsed).items():
        payload = json.dumps(rows, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
        entries[name.lower()] = {"message_type": name, "count": len(rows), "sha256": hashlib.sha256(payload).hexdigest(), "format": "json"}
    return {"schema_version": "flight-artifacts.v1", "status": "reliable" if entries else "insufficient_data", "artifacts": entries, "read_only": True}


def export_artifacts(parsed: dict[str, Any], output_dir: str | Path) -> Path:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    rows = artifact_rows(parsed)
    for name, values in rows.items():
        (destination / f"{name.lower()}.json").write_text(json.dumps(values, indent=2, sort_keys=True, default=str), encoding="utf-8")
    (destination / "manifest.json").write_text(json.dumps(artifact_manifest(parsed), indent=2, sort_keys=True), encoding="utf-8")
    return destination
