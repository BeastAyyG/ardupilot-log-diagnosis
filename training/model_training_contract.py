"""Integrity helpers shared by the grouped model-training command and tests."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from src.constants import FEATURE_NAMES, VALID_LABELS
from training.data_contract import (
    SYNTHETIC_SOURCE_TYPES,
    ambiguous_group_labels,
    require_known_source_types,
)

SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def configure_utf8_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass


def validate_group_label_contract(labels: pd.DataFrame, groups: pd.DataFrame) -> None:
    ambiguous = ambiguous_group_labels(labels, groups, VALID_LABELS)
    if not ambiguous:
        return
    details = "; ".join(
        f"{group}: {', '.join(names)}" for group, names in sorted(ambiguous.items())
    )
    raise ValueError(
        "Ambiguous source groups contain multiple primary labels; "
        "add explicit incident_id/source_group metadata or exclude them: " + details
    )


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_dataset_contract(
    dataset_report_path: str,
    *,
    features_csv: str,
    labels_csv: str,
    groups_csv: str,
) -> tuple[dict, dict]:
    report_path = Path(dataset_report_path)
    if not report_path.is_file():
        raise ValueError("A hash-bound dataset build or merge report is required.")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    schema = report.get("schema")
    if schema == "logdiagnosis.training-dataset-build/v2":
        contract = report
        source = "dataset_build_report"
    elif schema == "logdiagnosis.merged-training-dataset/v1":
        contract = report.get("extraction_contract")
        source = "merged_dataset_report"
        if not isinstance(contract, dict):
            raise ValueError("Merged dataset report lacks extraction_contract.")
    else:
        raise ValueError("Dataset report schema is unsupported for artifact training.")
    for key, path in (
        ("features_sha256", features_csv),
        ("labels_sha256", labels_csv),
        ("groups_sha256", groups_csv),
    ):
        if report.get(key) != sha256_file(path):
            raise ValueError(f"Dataset report is not bound to the current {key}.")
    try:
        window_sec = float(contract["window_sec"])
        overlap = float(contract["overlap"])
        if window_sec <= 0 or not 0 <= overlap < 1:
            raise ValueError
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            "Dataset build report must contain valid window_sec and overlap values."
        ) from exc
    window = {
        "version": 1,
        "window_sec": window_sec,
        "overlap": overlap,
        "include_full_log": True,
        "aggregation": "max_raw_probability",
        "source": source,
    }
    return window, report


def dataset_quality(report: dict) -> dict:
    quality_keys = (
        "source_group_policy",
        "unique_source_groups",
        "skipped_duplicate_sha256",
        "skipped_ambiguous_group",
        "ambiguous_source_groups",
        "ambiguous_source_group_files",
        "excluded_ambiguous_groups",
        "excluded_ambiguous_rows",
    )
    return {key: report[key] for key in quality_keys if key in report}


def load_window_contract(dataset_report_path: str) -> dict:
    """Legacy helper retained for callers that cannot produce an artifact."""

    report = json.loads(Path(dataset_report_path).read_text(encoding="utf-8"))
    contract = report.get("extraction_contract", report)
    try:
        window_sec = float(contract["window_sec"])
        overlap = float(contract["overlap"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Dataset report lacks a valid window contract.") from exc
    return {
        "version": 1,
        "window_sec": window_sec,
        "overlap": overlap,
        "include_full_log": True,
        "aggregation": "max_raw_probability",
        "source": "dataset_report",
    }


def load_dataset_quality(dataset_report_path: str) -> dict:
    report = json.loads(Path(dataset_report_path).read_text(encoding="utf-8"))
    return dataset_quality(report)


def validate_training_inputs(
    features: pd.DataFrame,
    labels: pd.DataFrame,
    groups: pd.DataFrame,
) -> None:
    if features.columns.tolist() != FEATURE_NAMES:
        raise ValueError(
            "Feature schema mismatch: rebuild the dataset with the current "
            "FeaturePipeline before training."
        )
    if labels.columns.tolist() != VALID_LABELS:
        raise ValueError(
            "Label schema mismatch: labels CSV must preserve "
            "constants.VALID_LABELS order."
        )
    if "source_log" not in groups.columns:
        raise ValueError("Groups CSV must contain a 'source_log' column.")


def validate_production_provenance(groups: pd.DataFrame, report: dict) -> None:
    """Reject research-only or incompletely attested rows before artifact fitting."""

    source_types = require_known_source_types(groups)
    synthetic = pd.Series(source_types).isin(SYNTHETIC_SOURCE_TYPES).to_numpy()
    real = source_types == "real"
    if bool(report.get("include_unverified_synthetic", False)):
        raise ValueError(
            "Research-override datasets are non-promotable and cannot train an artifact."
        )
    if "physical_flight_verified" not in groups.columns:
        raise ValueError(
            "Production training requires physical_flight_verified provenance."
        )
    physical = (
        groups["physical_flight_verified"]
        .fillna(False)
        .astype(str)
        .str.lower()
        .isin({"true", "1", "yes"})
        .to_numpy()
    )
    if np.any(real & ~physical):
        raise ValueError(
            "Every real training/evaluation row must be a verified physical flight."
        )
    required_synthetic = (
        "verification_status",
        "manifest_sha256",
        "parameter_schema_sha256",
        "artifact_sha256",
        "run_fingerprint",
        "manifestation_predicate_sha256",
    )
    for column in required_synthetic:
        if column not in groups.columns:
            raise ValueError(f"Production training groups lack {column}.")
    if np.any(
        synthetic
        & groups["verification_status"].fillna("").astype(str).ne("accepted").to_numpy()
    ):
        raise ValueError(
            "Synthetic artifact training requires accepted verification status."
        )
    for column in required_synthetic[1:]:
        values = groups[column].fillna("").astype(str).str.lower().to_numpy()
        if any(not SHA256_PATTERN.fullmatch(value) for value in values[synthetic]):
            raise ValueError(
                f"Verified synthetic rows contain invalid {column} values."
            )
    if "sha256" not in groups.columns:
        raise ValueError(
            "Production training groups lack source payload SHA256 values."
        )
    payload = groups["sha256"].fillna("").astype(str).str.lower().to_numpy()
    artifact = groups["artifact_sha256"].fillna("").astype(str).str.lower().to_numpy()
    if np.any(synthetic & (payload != artifact)):
        raise ValueError("Synthetic artifact SHA256 does not match its source payload.")
