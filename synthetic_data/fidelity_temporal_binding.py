"""Bind recomputed raw temporal evidence into feature fidelity reports."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .schema import sha256_file
from .temporal_fidelity import build_temporal_fidelity_report

MISSING_TEMPORAL_STATUS = (
    "Feature CSV cannot establish ACF/PSD/coherence/lag fidelity; "
    "raw-log evidence is required."
)


def build_bound_temporal_report(
    *,
    temporal_ledger_path: str | Path | None,
    temporal_design_path: str | Path | None,
    feature_design_path: str | Path | None,
    features_csv: str | Path,
    labels_csv: str | Path,
    groups_csv: str | Path,
    split_ledger_path: str | Path,
) -> dict[str, Any] | None:
    temporal_paths = (temporal_ledger_path, temporal_design_path)
    if not any(path is not None for path in temporal_paths):
        return None
    if not all(path is not None for path in temporal_paths):
        raise ValueError(
            "temporal ledger and temporal design must be supplied together"
        )
    if feature_design_path is None:
        raise ValueError("raw temporal fidelity requires the feature design manifest")
    report = build_temporal_fidelity_report(
        str(temporal_ledger_path),
        str(temporal_design_path),
        features_csv=features_csv,
        labels_csv=labels_csv,
        groups_csv=groups_csv,
        split_ledger_path=split_ledger_path,
    )
    if report["feature_fidelity_design_sha256"] != sha256_file(feature_design_path):
        raise ValueError(
            "temporal evidence is bound to a different feature fidelity design"
        )
    return report


def temporal_report_fields(report: dict[str, Any] | None) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "raw_temporal_checks_pass": False,
        "raw_temporal_status": MISSING_TEMPORAL_STATUS,
        "raw_temporal_report": None,
    }
    if report is not None:
        fields.update(
            {
                "candidate_manifest_sha256": report["candidate_manifest_sha256"],
                "raw_temporal_checks_pass": report["raw_temporal_checks_pass"],
                "raw_temporal_status": report["status"],
                "raw_temporal_report": report,
            }
        )
    return fields
