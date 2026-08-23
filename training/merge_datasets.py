"""Merge independently built training datasets without hiding provenance."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import pandas as pd

from src.constants import FEATURE_NAMES, VALID_LABELS
from training.data_contract import require_known_source_types
from training.dataset_build_contract import GROUP_COLUMNS

PROVENANCE_COLUMNS = GROUP_COLUMNS
BUILD_SCHEMA = "logdiagnosis.training-dataset-build/v2"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
CONTRACT_FIELDS = [
    "feature_schema_sha256",
    "label_schema_sha256",
    "extractor_source_sha256",
    "window_sec",
    "overlap",
    "transition_guard_sec",
    "window_policy",
    "include_full_log",
]


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_dataset(
    root: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    features_path = root / "features.csv"
    labels_path = root / "labels.csv"
    groups_path = root / "groups.csv"
    report_path = root / "dataset_build_report.json"
    if not report_path.is_file():
        raise ValueError(f"{root} lacks dataset_build_report.json")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("schema") != BUILD_SCHEMA:
        raise ValueError(f"{report_path} has an unsupported or legacy build contract")
    features = pd.read_csv(features_path)
    labels = pd.read_csv(labels_path)
    groups = pd.read_csv(groups_path)
    if features.columns.tolist() != FEATURE_NAMES:
        raise ValueError(f"{features_path} does not match runtime FEATURE_NAMES")
    if labels.columns.tolist() != VALID_LABELS:
        raise ValueError(f"{labels_path} does not match runtime VALID_LABELS")
    if not (len(features) == len(labels) == len(groups)):
        raise ValueError(f"Row counts differ in dataset {root}")
    for column in PROVENANCE_COLUMNS:
        if column not in groups.columns:
            raise ValueError(f"{groups_path} lacks required provenance column {column}")
    groups = groups[PROVENANCE_COLUMNS].copy()
    groups["source_type"] = require_known_source_types(groups)
    for column in ("source_log", "source_group", "lineage_root_id", "sha256"):
        if groups[column].fillna("").astype(str).str.strip().eq("").any():
            raise ValueError(f"{groups_path} contains blank {column} values")
    invalid_hashes = [
        value
        for value in groups["sha256"].astype(str).str.lower().unique()
        if not SHA256_PATTERN.fullmatch(value)
    ]
    if invalid_hashes:
        raise ValueError(f"{groups_path} contains invalid payload SHA256 values")
    synthetic = groups["source_type"].isin(
        ["sitl", "hil", "simulation", "feature_synthetic"]
    )
    if (
        synthetic & groups["verification_status"].fillna("").astype(str).ne("accepted")
    ).any():
        raise ValueError(f"{groups_path} contains unverified synthetic rows")
    for column in (
        "manifest_sha256",
        "parameter_schema_sha256",
        "artifact_sha256",
        "run_fingerprint",
        "manifestation_predicate_sha256",
    ):
        invalid = [
            value
            for value in groups.loc[synthetic, column]
            .fillna("")
            .astype(str)
            .str.lower()
            .unique()
            if not SHA256_PATTERN.fullmatch(value)
        ]
        if invalid:
            raise ValueError(f"{groups_path} contains invalid synthetic {column}")
    if (
        groups.loc[synthetic, "artifact_sha256"].astype(str).str.lower().to_numpy()
        != groups.loc[synthetic, "sha256"].astype(str).str.lower().to_numpy()
    ).any():
        raise ValueError(
            f"{groups_path} contains synthetic artifact/source hash mismatch"
        )
    file_hashes = {
        "features_sha256": _hash_file(features_path),
        "labels_sha256": _hash_file(labels_path),
        "groups_sha256": _hash_file(groups_path),
    }
    for name, digest in file_hashes.items():
        if report.get(name) != digest:
            raise ValueError(f"{report_path} is not bound to current {name}")
    contract = {field: report.get(field) for field in CONTRACT_FIELDS}
    if any(value is None for value in contract.values()):
        raise ValueError(f"{report_path} lacks a complete extraction contract")
    return (
        features,
        labels,
        groups,
        {
            **contract,
            **file_hashes,
            "include_unverified_synthetic": bool(
                report.get("include_unverified_synthetic", False)
            ),
        },
    )


def merge_datasets(input_dirs: list[str | Path], output_dir: str | Path) -> dict:
    """Merge dataset triplets and reject cross-input payload duplication."""

    if len(input_dirs) < 2:
        raise ValueError("At least two input datasets are required")
    feature_parts: list[pd.DataFrame] = []
    label_parts: list[pd.DataFrame] = []
    group_parts: list[pd.DataFrame] = []
    seen_hashes: set[str] = set()
    seen_groups: set[str] = set()
    inputs: list[dict] = []
    expected_contract: dict | None = None

    for raw_root in input_dirs:
        root = Path(raw_root)
        features, labels, groups, contract = _load_dataset(root)
        extraction_contract = {field: contract[field] for field in CONTRACT_FIELDS}
        if expected_contract is None:
            expected_contract = extraction_contract
        elif extraction_contract != expected_contract:
            differing = [
                field
                for field in CONTRACT_FIELDS
                if extraction_contract[field] != expected_contract[field]
            ]
            raise ValueError(
                f"Dataset {root} has an incompatible extraction contract: "
                + ", ".join(differing)
            )
        current_hashes = {
            value
            for value in groups["sha256"].fillna("").astype(str).str.strip()
            if value
        }
        overlap = sorted(seen_hashes & current_hashes)
        if overlap:
            raise ValueError(
                f"Dataset {root} duplicates {len(overlap)} payload SHA256 values from an earlier input"
            )
        seen_hashes.update(current_hashes)
        current_groups = set(groups["source_group"].astype(str))
        group_overlap = sorted(seen_groups & current_groups)
        if group_overlap:
            raise ValueError(
                f"Dataset {root} duplicates source groups from an earlier input"
            )
        seen_groups.update(current_groups)
        feature_parts.append(features)
        label_parts.append(labels)
        group_parts.append(groups)
        inputs.append(
            {
                "path": str(root),
                "rows": len(features),
                "source_incidents": int(groups["source_group"].nunique()),
                "features_sha256": _hash_file(root / "features.csv"),
                "labels_sha256": _hash_file(root / "labels.csv"),
                "groups_sha256": _hash_file(root / "groups.csv"),
                "dataset_build_report_sha256": _hash_file(
                    root / "dataset_build_report.json"
                ),
                "include_unverified_synthetic": contract[
                    "include_unverified_synthetic"
                ],
            }
        )

    features = pd.concat(feature_parts, ignore_index=True)
    labels = pd.concat(label_parts, ignore_index=True)
    groups = pd.concat(group_parts, ignore_index=True)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    features.to_csv(destination / "features.csv", index=False)
    labels.to_csv(destination / "labels.csv", index=False)
    groups.to_csv(destination / "groups.csv", index=False)

    report = {
        "schema": "logdiagnosis.merged-training-dataset/v1",
        "inputs": inputs,
        "rows": len(features),
        "source_incidents": int(groups["source_group"].nunique()),
        "source_type_distribution": dict(Counter(groups["source_type"])),
        "unique_payload_sha256": len(seen_hashes),
        "extraction_contract": expected_contract,
        "evaluation_policy": "synthetic source types are training-only",
        "include_unverified_synthetic": any(
            item["include_unverified_synthetic"] for item in inputs
        ),
    }
    report["features_sha256"] = _hash_file(destination / "features.csv")
    report["labels_sha256"] = _hash_file(destination / "labels.csv")
    report["groups_sha256"] = _hash_file(destination / "groups.csv")
    (destination / "merge_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", required=True, dest="inputs")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(json.dumps(merge_datasets(args.inputs, args.output), indent=2))


if __name__ == "__main__":
    main()
