"""Helper functions for leakage-safe diagnosis candidate training."""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from src.constants import VALID_LABELS
from training.data_contract import (
    SYNTHETIC_SOURCE_TYPES,
    primary_label_for_row,
)


def hash_values(values: np.ndarray) -> list[str]:
    return sorted(
        {hashlib.sha256(str(value).encode("utf-8")).hexdigest() for value in values}
    )


def labels(labels: pd.DataFrame, groups: pd.DataFrame) -> np.ndarray:
    output: list[str] = []
    for position, (_, row) in enumerate(labels.iterrows()):
        preferred = (
            groups.iloc[position].get("primary_label", "")
            if "primary_label" in groups.columns
            else ""
        )
        output.append(
            primary_label_for_row(row, preferred=preferred, allowed=VALID_LABELS)
        )
    return np.asarray(output)


def require_lineages(groups: pd.DataFrame) -> np.ndarray:
    if "lineage_root_id" not in groups.columns:
        raise ValueError("Production training requires lineage_root_id.")
    values = groups["lineage_root_id"].fillna("").astype(str).str.strip().to_numpy()
    if any(not value for value in values):
        raise ValueError("Production training contains blank lineage_root_id values.")
    return values


def partition_mask(
    assignments: dict[str, str],
    source_groups: np.ndarray,
    source_types: np.ndarray,
    name: str,
) -> np.ndarray:
    return np.asarray(
        [
            source_type == "real" and assignments.get(str(group)) == name
            for group, source_type in zip(source_groups, source_types)
        ]
    )


def validate_partition_support(
    primary: np.ndarray,
    lineages: np.ndarray,
    mask: np.ndarray,
    classes: list[str],
    *,
    minimum: int,
    partition: str,
) -> None:
    insufficient = {
        label: len(set(lineages[mask & (primary == label)].tolist()))
        for label in classes
        if len(set(lineages[mask & (primary == label)].tolist())) < minimum
    }
    if insufficient:
        details = ", ".join(f"{label}={count}" for label, count in insufficient.items())
        raise ValueError(
            f"{partition} lacks independent lineage support (minimum {minimum}): {details}"
        )


def validate_descendants(
    groups: pd.DataFrame,
    source_types: np.ndarray,
    protected_lineages: set[str],
    training_lineages: set[str] | None = None,
) -> None:
    synthetic = np.isin(source_types, tuple(SYNTHETIC_SOURCE_TYPES))
    if not synthetic.any():
        return
    if "conditioning_real_lineage_id" not in groups.columns:
        raise ValueError("Synthetic rows lack conditioning_real_lineage_id provenance.")
    parents = (
        groups["conditioning_real_lineage_id"]
        .fillna("")
        .astype(str)
        .str.strip()
        .to_numpy()
    )
    if "conditioning_mode" not in groups.columns:
        raise ValueError("Synthetic rows lack conditioning_mode provenance.")
    modes = groups["conditioning_mode"].fillna("").astype(str).str.strip().to_numpy()
    if any(
        value not in {"pure_simulation", "real_conditioned"}
        for value in modes[synthetic]
    ):
        raise ValueError("Synthetic rows contain an invalid conditioning_mode.")
    if np.any(synthetic & (modes == "pure_simulation") & (parents != "")):
        raise ValueError("Pure-simulation rows cannot name a conditioning lineage.")
    if training_lineages is not None and any(
        not parent or parent not in training_lineages
        for parent in parents[synthetic & (modes == "real_conditioned")]
    ):
        raise ValueError(
            "Real-conditioned synthetic rows must originate from real_train lineages."
        )
    overlap = sorted(
        {value for value in parents[synthetic] if value} & protected_lineages
    )
    if overlap:
        raise ValueError(
            "Synthetic training descendants originate from protected real lineages: "
            + ", ".join(overlap[:10])
        )
