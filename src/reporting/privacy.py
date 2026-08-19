"""Privacy-preserving report and expert hand-off bundle helpers."""

from __future__ import annotations

import copy
import base64
import json
import zipfile
from pathlib import Path
from typing import Any

from src.reporting.plot_export import generate_plot
from src.reporting.graph_pack import generate_graph_pack


def scrub_report(report: dict[str, Any], *, remove_gps: bool = True, redact_parameters: bool = True) -> dict[str, Any]:
    """Return a shareable copy without coordinates or sensitive parameter values."""

    result = copy.deepcopy(report)
    if remove_gps:
        sensitive_keys = {"lat", "lng", "latitude", "longitude", "Lat", "Lng", "location", "home"}

        def scrub_node(node: Any) -> Any:
            if isinstance(node, dict):
                return {key: scrub_node(value) for key, value in node.items() if str(key) not in sensitive_keys}
            if isinstance(node, list):
                return [scrub_node(value) for value in node]
            return node

        result = scrub_node(result)
    if redact_parameters:
        hardware = result.get("hardware_report", {})
        parameters = hardware.get("parameters", {}) if isinstance(hardware, dict) else {}
        if isinstance(parameters, dict):
            lines = parameters.get("lines")
            if isinstance(lines, list):
                parameters["lines"] = [line for line in lines if not any(token in str(line).upper() for token in ("HOME", "SYSID", "SERIAL", "AUTH"))]
    result["privacy"] = {"gps_removed": remove_gps, "sensitive_parameters_redacted": redact_parameters}
    return result


def export_expert_bundle(report: dict[str, Any], output_path: str | Path, *, log_path: str | Path | None = None, scrub: bool = True) -> Path:
    """Write JSON, a human-readable hand-off note, and optionally the source log."""

    destination = Path(output_path)
    payload = scrub_report(report) if scrub else report
    note = [
        "ArduPilot Log Diagnosis expert hand-off",
        "Read-only bundle: no parameters or vehicle state were changed.",
        f"Report schema: {payload.get('schema_version', 'unknown')}",
        "Review the evidence, input hash, and data-availability blockers before acting.",
    ]
    if log_path and scrub:
        note.append("The source binary was intentionally omitted because this bundle is privacy-scrubbed; use --no-scrub only after reviewing the privacy impact.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    bundle_files = ["analysis-report.json", "README.txt", "manifest.json", "plots/health.png", "plots/diagnoses.png", "plots/graph-pack.html"]
    source = Path(log_path) if log_path else None
    if source and not scrub and source.exists() and source.is_file() and source.stat().st_size <= 512 * 1024 * 1024:
        bundle_files.append(f"input/{source.name}")
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("analysis-report.json", json.dumps(payload, indent=2, sort_keys=True, default=str))
        archive.writestr("README.txt", "\n".join(note) + "\n")
        archive.writestr("manifest.json", json.dumps({"schema_version": "expert-bundle.v1", "files": bundle_files, "privacy": payload.get("privacy", {}), "read_only": True}, indent=2, sort_keys=True))
        for kind in ("health", "diagnoses"):
            plot = generate_plot(payload, kind=kind)
            if plot.get("status") == "reliable":
                archive.writestr(f"plots/{kind}.png", base64.b64decode(plot["data"]))
        archive.writestr("plots/graph-pack.html", generate_graph_pack(payload)["html"])
        if log_path and not scrub:
            if source and source.exists() and source.is_file() and source.stat().st_size <= 512 * 1024 * 1024:
                archive.write(source, arcname=f"input/{source.name}")
    return destination
