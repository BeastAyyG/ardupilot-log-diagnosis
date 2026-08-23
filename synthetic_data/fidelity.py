"""Conditional sim-real diagnostics that never inspect confirmation evidence."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.constants import FEATURE_NAMES
from training.data_contract import (
    effective_group_values,
    primary_label_for_row,
    require_known_source_types,
)

from .fidelity_bounds import simultaneous_worst_stratum_bounds
from .fidelity_statistics import (
    collapse_lineage_units,
    conditional_feature_test_family,
    conditional_real_real_envelopes,
    feature_distances,
)
from .fidelity_temporal_binding import (
    build_bound_temporal_report,
    temporal_report_fields,
)
from .schema import sha256_file
from .splits import load_and_validate_ledger

FIDELITY_SCHEMA = "logdiagnosis.synthetic-fidelity/v2"
DESIGN_SCHEMA = "logdiagnosis.fidelity-design-manifest/v1"
STRATIFIERS = (
    "primary_label",
    "flight_phase",
    "vehicle_frame",
    "firmware_commit",
    "simulation_family",
)


def _load_design_manifest(path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"design manifest is unreadable: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ValueError("design manifest root must be an object")
    if manifest.get("schema") != DESIGN_SCHEMA:
        raise ValueError("unsupported fidelity design manifest schema")
    required = manifest.get("required_strata")
    if (
        not isinstance(required, list)
        or not required
        or not all(isinstance(item, dict) for item in required)
    ):
        raise ValueError("design manifest requires a non-empty required_strata list")
    for item in required:
        for name in STRATIFIERS:
            value = item.get(name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"design manifest stratum lacks a valid {name} stratifier"
                )
    minimum = manifest.get("minimum_units_per_domain_per_stratum")
    if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 1:
        raise ValueError(
            "design manifest requires an integer minimum_units_per_domain_per_stratum >= 1"
        )
    return manifest


def evaluate_design_manifest(
    conditional_rows: list[dict[str, Any]],
    design_manifest_path: str | Path,
) -> dict[str, Any]:
    """Score preregistered strata against measured conditional support."""

    path = Path(design_manifest_path)
    manifest = _load_design_manifest(path)
    minimum = int(manifest["minimum_units_per_domain_per_stratum"])
    by_key = {
        tuple(str(row.get(name, "")) for name in STRATIFIERS): row
        for row in conditional_rows
    }
    evaluated = 0
    missing_detail: list[dict[str, str]] = []
    for entry in manifest["required_strata"]:
        key = tuple(str(entry[name]) for name in STRATIFIERS)
        row = by_key.get(key)
        supported = (
            row is not None
            and row.get("eligible") is True
            and int(row.get("real_units", 0)) >= minimum
            and int(row.get("synthetic_units", 0)) >= minimum
        )
        if supported:
            evaluated += 1
        else:
            missing_detail.append({name: str(entry[name]) for name in STRATIFIERS})
    return {
        "schema": DESIGN_SCHEMA,
        "design_manifest_sha256": sha256_file(path),
        "minimum_units_per_domain_per_stratum": minimum,
        "design_required_strata": len(manifest["required_strata"]),
        "evaluated_required_strata": evaluated,
        "missing_required_strata": len(missing_detail),
        "missing_strata_detail": missing_detail,
    }


def _primary(labels: pd.DataFrame, groups: pd.DataFrame) -> np.ndarray:
    values: list[str] = []
    for position, (_, row) in enumerate(labels.iterrows()):
        preferred = (
            groups.iloc[position].get("primary_label", "")
            if "primary_label" in groups.columns
            else ""
        )
        values.append(
            primary_label_for_row(
                row,
                preferred=preferred,
                allowed=labels.columns.tolist(),
            )
        )
    return np.asarray(values)


def _column(groups: pd.DataFrame, name: str) -> np.ndarray:
    if name not in groups.columns:
        return np.asarray([""] * len(groups))
    return groups[name].fillna("").astype(str).str.strip().to_numpy()


def _units(
    features: pd.DataFrame,
    lineages: np.ndarray,
    primary: np.ndarray,
    indices: np.ndarray,
    metadata: dict[str, np.ndarray],
) -> tuple[np.ndarray, list[dict[str, str]]]:
    positions_by_key: dict[tuple[str, str], list[int]] = defaultdict(list)
    for position in indices:
        positions_by_key[(str(lineages[position]), str(primary[position]))].append(
            int(position)
        )
    rows: list[np.ndarray] = []
    records: list[dict[str, str]] = []
    for (lineage, label), positions in sorted(positions_by_key.items()):
        rows.append(np.median(features.iloc[positions].to_numpy(dtype=float), axis=0))
        record = {"lineage_root_id": lineage, "primary_label": label}
        for name, values in metadata.items():
            observed = {str(values[position]) for position in positions}
            if len(observed) != 1:
                raise ValueError(
                    f"lineage-label unit has mixed {name}: {lineage}/{label}"
                )
            record[name] = next(iter(observed))
        records.append(record)
    return np.asarray(rows), records


def _conditional_reports(
    real: np.ndarray,
    synthetic: np.ndarray,
    real_records: list[dict[str, str]],
    synthetic_records: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], float]:
    results: list[dict[str, Any]] = []
    covered = 0
    for synthetic_key in sorted(
        {
            (
                record["primary_label"],
                record["flight_phase"],
                record["vehicle_frame"],
                record["firmware_commit"],
                record["simulation_family"],
            )
            for record in synthetic_records
        }
    ):
        label, phase, frame, firmware, family = synthetic_key
        synthetic_positions = [
            index
            for index, record in enumerate(synthetic_records)
            if (
                record["primary_label"],
                record["flight_phase"],
                record["vehicle_frame"],
                record["firmware_commit"],
                record["simulation_family"],
            )
            == synthetic_key
        ]
        real_positions = [
            index
            for index, record in enumerate(real_records)
            if (
                record["primary_label"],
                record["flight_phase"],
                record["vehicle_frame"],
                record["firmware_commit"],
            )
            == (label, phase, frame, firmware)
        ]
        complete_key = all((label, phase, frame, firmware, family))
        eligible = (
            complete_key and len(real_positions) >= 3 and len(synthetic_positions) >= 3
        )
        result: dict[str, Any] = {
            "primary_label": label,
            "flight_phase": phase,
            "vehicle_frame": frame,
            "firmware_commit": firmware,
            "simulation_family": family,
            "real_units": len(real_positions),
            "synthetic_units": len(synthetic_positions),
            "eligible": eligible,
        }
        if eligible:
            distances = feature_distances(
                real[np.asarray(real_positions)],
                synthetic[np.asarray(synthetic_positions)],
            )
            result["median_normalized_wasserstein"] = float(
                np.median([item["normalized_wasserstein"] for item in distances])
            )
            result["worst_features"] = distances[:10]
            covered += len(synthetic_positions)
        results.append(result)
    coverage = covered / len(synthetic_records) if synthetic_records else 0.0
    return results, float(coverage)


def build_fidelity_report(
    features_csv: str | Path,
    labels_csv: str | Path,
    groups_csv: str | Path,
    split_ledger: str | Path,
    *,
    output_path: str | Path | None = None,
    design_manifest_path: str | Path | None = None,
    temporal_ledger_path: str | Path | None = None,
    temporal_design_path: str | Path | None = None,
) -> dict[str, Any]:
    """Compare verified simulation with real training data conditionally."""

    features_path, labels_path, groups_path = map(
        Path, (features_csv, labels_csv, groups_csv)
    )
    features = pd.read_csv(features_path)
    labels = pd.read_csv(labels_path)
    groups = pd.read_csv(groups_path)
    if not (len(features) == len(labels) == len(groups)):
        raise ValueError("dataset triplet row counts differ")
    if features.columns.tolist() != FEATURE_NAMES:
        raise ValueError("feature CSV does not match the runtime feature schema")
    if not np.isfinite(features.to_numpy(dtype=float)).all():
        raise ValueError("features contain non-finite values")
    source_types = require_known_source_types(groups)
    source_groups = effective_group_values(groups)
    lineages = _column(groups, "lineage_root_id")
    if any(not value for value in lineages):
        raise ValueError("fidelity analysis requires lineage_root_id")
    primary = _primary(labels, groups)
    ledger = load_and_validate_ledger(split_ledger, labels_path, groups_path)
    temporal_report = build_bound_temporal_report(
        temporal_ledger_path=temporal_ledger_path,
        temporal_design_path=temporal_design_path,
        feature_design_path=design_manifest_path,
        features_csv=features_path,
        labels_csv=labels_path,
        groups_csv=groups_path,
        split_ledger_path=split_ledger,
    )
    temporal_fields = temporal_report_fields(temporal_report)
    declared = set(ledger["declared_model_classes"])
    assignments = ledger["source_group_assignments"]
    real_indices = np.asarray(
        [
            index
            for index, (group, source_type, label) in enumerate(
                zip(source_groups, source_types, primary)
            )
            if source_type == "real"
            and label in declared
            and assignments.get(str(group)) == "real_train"
        ],
        dtype=int,
    )
    verification = _column(groups, "verification_status")
    synthetic_indices = np.asarray(
        [
            index
            for index, (source_type, label) in enumerate(zip(source_types, primary))
            if source_type in {"sitl", "hil", "simulation"}
            and label in declared
            and verification[index] == "accepted"
        ],
        dtype=int,
    )
    if not len(real_indices):
        raise ValueError("no real training rows are available for fidelity analysis")
    if not len(synthetic_indices):
        report = {
            "schema": FIDELITY_SCHEMA,
            "status": "blocked_no_verified_synthetic_data",
            "real_training_rows": int(len(real_indices)),
            "verified_synthetic_rows": 0,
            "source_classifier_permutation_draws": 0,
            "source_classifier_permutation_p_value": None,
            "nonlinear_c2st_complete": False,
            "mmd_complete": False,
            "worst_stratum_bounds_pass": False,
            "stratifiers": list(STRATIFIERS),
            **temporal_fields,
            "release_claim": "none",
        }
        if design_manifest_path is not None:
            design = evaluate_design_manifest([], design_manifest_path)
            report["design_evaluation"] = design
            report.update(
                {
                    key: design[key]
                    for key in (
                        "design_manifest_sha256",
                        "design_required_strata",
                        "evaluated_required_strata",
                        "missing_required_strata",
                        "minimum_units_per_domain_per_stratum",
                    )
                }
            )
        if output_path:
            destination = Path(output_path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(
                json.dumps(report, indent=2) + "\n", encoding="utf-8"
            )
        return report

    metadata = {
        name: _column(groups, name) for name in STRATIFIERS if name != "primary_label"
    }
    real, real_records = _units(features, lineages, primary, real_indices, metadata)
    synthetic, synthetic_records = _units(
        features, lineages, primary, synthetic_indices, metadata
    )
    real_global = collapse_lineage_units(real, real_records)
    synthetic_global = collapse_lineage_units(synthetic, synthetic_records)
    global_distances = feature_distances(real_global, synthetic_global)
    feature_test_family = conditional_feature_test_family(
        real,
        synthetic,
        real_records,
        synthetic_records,
    )
    worst_stratum_bounds = simultaneous_worst_stratum_bounds(
        real,
        synthetic,
        real_records,
        synthetic_records,
    )
    conditional_envelopes = conditional_real_real_envelopes(
        real,
        synthetic,
        real_records,
        synthetic_records,
    )
    conditional, conditional_coverage = _conditional_reports(
        real, synthetic, real_records, synthetic_records
    )
    outside_envelope = conditional_envelopes.get(
        "maximum_features_outside_real_real_95_envelope"
    )
    missing_metadata = sorted(
        name
        for name in STRATIFIERS[1:]
        if any(not record[name] for record in real_records + synthetic_records)
    )
    normalized = np.asarray(
        [item["normalized_wasserstein"] for item in global_distances]
    )
    status = (
        "measured_conditionally_not_promoted"
        if conditional_coverage == 1.0 and not missing_metadata
        else "blocked_incomplete_conditional_fidelity"
    )
    design = None
    if design_manifest_path is not None:
        design = evaluate_design_manifest(conditional, design_manifest_path)
        if design["missing_required_strata"] > 0:
            status = "blocked_incomplete_conditional_fidelity"
    source_distinguishability = feature_test_family.get(
        "family_max_distinguishability_auc"
    )
    report = {
        "schema": FIDELITY_SCHEMA,
        "status": status,
        "comparison_scope": "real_train_lineages_vs_verified_synthetic_lineages",
        "real_units": len(real_global),
        "synthetic_units": len(synthetic_global),
        "global_unit": "lineage_root_id",
        "global_lineage_arm_aggregation": "median_across_lineage_label_arms",
        "source_classifier_raw_auc": feature_test_family.get("worst_linear_raw_auc"),
        "source_distinguishability_auc": source_distinguishability,
        "source_classifier_protocol": feature_test_family,
        "source_classifier_permutation_draws": feature_test_family.get(
            "permutation_draws", 0
        ),
        "source_classifier_permutation_p_value": feature_test_family.get(
            "familywise_source_classifier_permutation_p_value"
        ),
        "nonlinear_c2st_complete": (
            feature_test_family.get("nonlinear_c2st_complete") is True
        ),
        "mmd_complete": feature_test_family.get("mmd_complete") is True,
        "mmd_protocol": {
            "scope": "within_preregistered_comparable_strata",
            "strata": [
                {"stratum": row["stratum"], "mmd": row["mmd"]}
                for row in feature_test_family.get("strata", [])
            ],
        },
        "worst_stratum_bounds_pass": bool(
            worst_stratum_bounds.get("complete") and worst_stratum_bounds.get("pass")
        ),
        "worst_stratum_bounds": worst_stratum_bounds,
        "stratifiers": list(STRATIFIERS),
        "conditional_strata_coverage": conditional_coverage,
        "conditional_strata": conditional,
        "missing_stratifier_metadata": missing_metadata,
        "features_outside_real_real_95_envelope": outside_envelope,
        "real_real_envelope_status": conditional_envelopes["status"],
        "real_real_envelope_protocol": conditional_envelopes,
        "median_normalized_wasserstein_exploratory": float(np.median(normalized)),
        "worst_features_exploratory": global_distances[:20],
        **temporal_fields,
        "interpretation": (
            "Distinguishability is 0.5 + abs(AUC - 0.5), so values below 0.5 are "
            "not mistaken for good fidelity. Fidelity never establishes utility."
        ),
        "release_claim": "none",
    }
    if design is not None:
        report["design_evaluation"] = design
        report.update(
            {
                key: design[key]
                for key in (
                    "design_manifest_sha256",
                    "design_required_strata",
                    "evaluated_required_strata",
                    "missing_required_strata",
                    "minimum_units_per_domain_per_stratum",
                )
            }
        )
    if source_distinguishability is not None and not math.isfinite(
        source_distinguishability
    ):
        report["source_distinguishability_auc"] = None
    if output_path:
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report
