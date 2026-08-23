"""Pure helpers for schema-v3 candidate validation before model loading."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from synthetic_data.schema import canonical_json_bytes, sha256_bytes
from training.data_contract import (
    SYNTHETIC_SOURCE_TYPES,
    effective_group_values,
    primary_label_for_row,
    require_known_source_types,
)


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def valid_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def hash_values(values: np.ndarray) -> list[str]:
    return sorted({hashlib.sha256(str(value).encode()).hexdigest() for value in values})


def hash_schema(values: list[str]) -> str:
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def extraction_contract_sha256(window_contract: dict[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes(window_contract))


def primary_labels(
    labels: pd.DataFrame, groups: pd.DataFrame, classes: list[str]
) -> np.ndarray:
    values = [
        primary_label_for_row(
            row,
            preferred=(
                groups.iloc[position].get("primary_label", "")
                if "primary_label" in groups.columns
                else ""
            ),
            allowed=classes,
        )
        for position, (_, row) in enumerate(labels.iterrows())
    ]
    return np.asarray(values)


def partition_bindings(
    labels: pd.DataFrame,
    groups: pd.DataFrame,
    ledger: dict[str, Any],
    classes: list[str],
) -> dict[str, Any]:
    if "lineage_root_id" not in groups.columns:
        raise ValueError("Groups CSV lacks lineage_root_id.")
    lineages = groups["lineage_root_id"].fillna("").astype(str).str.strip().to_numpy()
    if any(not value for value in lineages):
        raise ValueError("Groups CSV contains blank lineage_root_id values.")
    source_types = require_known_source_types(groups)
    source_groups = effective_group_values(groups)
    primary = primary_labels(labels, groups, classes)
    supported = np.isin(primary, classes)
    assignments = ledger["source_group_assignments"]
    real = source_types == "real"
    real_train = np.asarray(
        [
            kind == "real" and assignments.get(str(group)) == "real_train"
            for group, kind in zip(source_groups, source_types)
        ]
    )
    calibration = np.asarray(
        [
            kind == "real" and assignments.get(str(group)) == "real_calibration"
            for group, kind in zip(source_groups, source_types)
        ]
    )
    development_test = np.asarray(
        [
            kind == "real" and assignments.get(str(group)) == "real_lockbox"
            for group, kind in zip(source_groups, source_types)
        ]
    )
    verified = (
        groups.get("verification_status", pd.Series("", index=groups.index))
        .fillna("")
        .astype(str)
        .eq("accepted")
        .to_numpy()
    )
    synthetic = np.isin(source_types, tuple(SYNTHETIC_SOURCE_TYPES)) & verified
    train = (real_train | synthetic) & supported
    calibration &= supported
    development_test &= supported
    if np.any((train & calibration) | (train & development_test)):
        raise ValueError("Recomputed train/calibration/development partitions overlap.")
    test_labels: dict[str, str] = {}
    for lineage in sorted(set(lineages[development_test].tolist())):
        found = set(primary[development_test & (lineages == lineage)].tolist())
        if len(found) != 1:
            raise ValueError(f"Development lineage {lineage} has mixed labels.")
        test_labels[lineage] = next(iter(found))
    return {
        "primary": primary,
        "lineages": lineages,
        "source_groups": source_groups,
        "source_types": source_types,
        "train_mask": train,
        "calibration_mask": calibration,
        "test_mask": development_test,
        "train_source_group_hashes": hash_values(source_groups[train]),
        "calibration_source_group_hashes": hash_values(source_groups[calibration]),
        "test_source_group_hashes": hash_values(source_groups[development_test]),
        "train_lineage_hashes": hash_values(lineages[train]),
        "calibration_lineage_hashes": hash_values(lineages[calibration]),
        "test_lineage_hashes": hash_values(lineages[development_test]),
        "test_source_incident_group_count": len(
            set(source_groups[development_test].tolist())
        ),
        "test_lineage_count": len(test_labels),
        "test_per_class_support": {
            name: sum(value == name for value in test_labels.values())
            for name in classes
        },
        "test_is_real_only": bool(np.all(real[development_test])),
    }


def metric_errors(expected: Any, observed: Any, path: str = "metrics") -> list[str]:
    if isinstance(expected, dict) and isinstance(observed, dict):
        if set(expected) != set(observed):
            return [f"{path} keys differ from recomputed metrics."]
        return [
            error
            for key in expected
            for error in metric_errors(expected[key], observed[key], f"{path}.{key}")
        ]
    if expected is None or observed is None:
        return [] if expected is observed else [f"{path} differs from recomputation."]
    if (
        isinstance(expected, (int, float))
        and not isinstance(expected, bool)
        and isinstance(observed, (int, float))
        and not isinstance(observed, bool)
    ):
        return (
            []
            if math.isfinite(float(expected))
            and math.isfinite(float(observed))
            and math.isclose(float(expected), float(observed), abs_tol=1e-12)
            else [f"{path} differs from recomputation."]
        )
    return [] if expected == observed else [f"{path} differs from recomputation."]
