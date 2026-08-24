"""Immutable lineage-safe real train/calibration/lockbox split ledgers."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, cast

import pandas as pd

from training.data_contract import (
    effective_group_values,
    primary_label_for_row,
    require_known_source_types,
)

SPLIT_SCHEMA = "logdiagnosis.real-incident-split/v2"
MINIMUM_TRAIN_LINEAGES = 2
MINIMUM_CALIBRATION_LINEAGES = 2
MINIMUM_DEVELOPMENT_TEST_LINEAGES = 1
MINIMUM_TOTAL_LINEAGES = (
    MINIMUM_TRAIN_LINEAGES
    + MINIMUM_CALIBRATION_LINEAGES
    + MINIMUM_DEVELOPMENT_TEST_LINEAGES
)


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _rank(seed: int, label: str, lineage: str) -> str:
    return hashlib.sha256(f"{seed}:{label}:{lineage}".encode()).hexdigest()


def _primary_labels(labels: pd.DataFrame, groups: pd.DataFrame) -> list[str]:
    allowed = labels.columns.tolist()
    output: list[str] = []
    for position, (_, row) in enumerate(labels.iterrows()):
        preferred = (
            groups.iloc[position].get("primary_label", "")
            if "primary_label" in groups.columns
            else ""
        )
        output.append(primary_label_for_row(row, preferred=preferred, allowed=allowed))
    return output


def _valid_synthetic_pair(
    groups: pd.DataFrame,
    positions: list[int],
    primary: list[str],
) -> bool:
    required = {"source_group", "pair_role", "run_id", "paired_with"}
    if not required.issubset(groups.columns):
        return False
    records: dict[str, tuple[str, str, str, str]] = {}
    for position in positions:
        row = groups.iloc[position]
        group = str(row.get("source_group", "") or "").strip()
        record = (
            str(row.get("pair_role", "") or "").strip(),
            str(row.get("run_id", "") or "").strip(),
            str(row.get("paired_with", "") or "").strip(),
            primary[position],
        )
        if not group or (group in records and records[group] != record):
            return False
        records[group] = record
    if len(records) != 2:
        return False
    by_role = {record[0]: record for record in records.values()}
    if set(by_role) != {"sham_control", "intervention"}:
        return False
    sham = by_role["sham_control"]
    intervention = by_role["intervention"]
    return bool(
        sham[1]
        and intervention[1]
        and sham[2] == intervention[1]
        and intervention[2] == sham[1]
        and sham[3] == "healthy"
        and intervention[3] not in {"", "healthy"}
    )


def create_split_ledger(
    labels_csv: str | Path,
    groups_csv: str | Path,
    output_path: str | Path,
    *,
    seed: int = 20260823,
    declared_classes: list[str] | None = None,
) -> dict[str, Any]:
    """Freeze real lineage roots and a task taxonomy before model evaluation."""

    labels_path = Path(labels_csv)
    groups_path = Path(groups_csv)
    labels = pd.read_csv(labels_path)
    groups = pd.read_csv(groups_path)
    if len(labels) != len(groups):
        raise ValueError("labels and groups row counts differ")
    source_types = require_known_source_types(groups)
    source_groups = effective_group_values(groups)
    lineages = (
        groups["lineage_root_id"].fillna("").astype(str).str.strip().to_numpy()
        if "lineage_root_id" in groups.columns
        else source_groups
    )
    if any(not value for value in lineages):
        raise ValueError("every row must have a lineage_root_id")
    primary = _primary_labels(labels, groups)

    lineage_labels: dict[str, set[str]] = defaultdict(set)
    lineage_groups: dict[str, set[str]] = defaultdict(set)
    lineage_types: dict[str, set[str]] = defaultdict(set)
    lineage_positions: dict[str, list[int]] = defaultdict(list)
    for position, (lineage, group, label, source_type) in enumerate(
        zip(lineages, source_groups, primary, source_types)
    ):
        if label:
            lineage_labels[str(lineage)].add(label)
        lineage_groups[str(lineage)].add(str(group))
        lineage_types[str(lineage)].add(str(source_type))
        lineage_positions[str(lineage)].append(position)
    invalid: list[str] = []
    for lineage in lineage_labels:
        types = lineage_types[lineage]
        labels_for_lineage = lineage_labels[lineage]
        accepted = False
        if "verification_status" in groups.columns:
            accepted = any(
                str(groups.iloc[position].get("verification_status", ""))
                .strip()
                .lower()
                == "accepted"
                for position in lineage_positions[lineage]
            )
        if len(types) != 1:
            invalid.append(lineage)
        elif types == {"real"} and len(labels_for_lineage) != 1:
            invalid.append(lineage)
        elif (
            types != {"real"}
            and accepted
            and any(label != "healthy" for label in labels_for_lineage)
            and not _valid_synthetic_pair(
                groups, lineage_positions[lineage], primary
            )
        ):
            invalid.append(lineage)
        elif len(labels_for_lineage) > 1 and not _valid_synthetic_pair(
            groups, lineage_positions[lineage], primary
        ):
            invalid.append(lineage)
    if invalid:
        raise ValueError(
            "lineage roots have invalid mixed labels, types, or pair metadata: "
            + ", ".join(invalid[:10])
        )

    by_label: dict[str, list[str]] = defaultdict(list)
    for lineage, label_set in lineage_labels.items():
        if lineage_types[lineage] == {"real"}:
            by_label[next(iter(label_set))].append(lineage)
    supported_real_classes = sorted(
        label for label, values in by_label.items() if len(values) >= MINIMUM_TOTAL_LINEAGES
    )
    if declared_classes is None:
        frozen_classes = supported_real_classes
        declaration_source = "supported_real_taxonomy_at_split_freeze"
    else:
        frozen_classes = sorted(set(declared_classes))
        if not frozen_classes or any(not value for value in frozen_classes):
            raise ValueError("declared_classes must contain non-empty unique labels")
        unknown = sorted(set(frozen_classes) - set(labels.columns))
        if unknown:
            raise ValueError(
                "declared classes are absent from the label schema: "
                + ", ".join(unknown)
            )
        insufficient = {
            label: len(by_label.get(label, []))
            for label in frozen_classes
            if len(by_label.get(label, [])) < MINIMUM_TOTAL_LINEAGES
        }
        if insufficient:
            details = ", ".join(
                f"{label}={count}" for label, count in sorted(insufficient.items())
            )
            raise ValueError(
                "declared classes lack the required 2 train / 2 calibration / "
                f"1 development-test real lineages: {details}"
            )
        declaration_source = "caller_preregistered"
    assignments: dict[str, str] = {}
    unsupported: dict[str, str] = {}
    for label, values in sorted(by_label.items()):
        ordered = sorted(values, key=lambda value: _rank(seed, label, value))
        count = len(ordered)
        if count < MINIMUM_TOTAL_LINEAGES:
            test_count = calibration_count = 0
            unsupported[label] = (
                "fewer than five independent real lineages for 2 train / "
                "2 calibration / 1 development-test allocation"
            )
            for lineage in ordered:
                assignments[lineage] = "real_unassigned"
            continue
        else:
            test_count = max(1, round(count * 0.20))
            calibration_count = max(2, round(count * 0.20))
            while count - test_count - calibration_count < MINIMUM_TRAIN_LINEAGES:
                if test_count > MINIMUM_DEVELOPMENT_TEST_LINEAGES:
                    test_count -= 1
                elif calibration_count > MINIMUM_CALIBRATION_LINEAGES:
                    calibration_count -= 1
                else:
                    break
        for lineage in ordered[:test_count]:
            assignments[lineage] = "real_lockbox"
        for lineage in ordered[test_count : test_count + calibration_count]:
            assignments[lineage] = "real_calibration"
        for lineage in ordered[test_count + calibration_count :]:
            assignments[lineage] = "real_train"

    group_assignments = {
        group: assignments[lineage]
        for lineage, source_type_set in lineage_types.items()
        if source_type_set == {"real"}
        for group in lineage_groups[lineage]
    }
    counts = Counter(assignments.values())
    class_partition_counts: dict[str, dict[str, int]] = {}
    for label, label_lineages in sorted(by_label.items()):
        class_partition_counts[label] = dict(
            sorted(Counter(assignments[value] for value in label_lineages).items())
        )
    payload = {
        "schema": SPLIT_SCHEMA,
        "frozen": True,
        "seed": int(seed),
        "labels_sha256": _file_hash(labels_path),
        "groups_sha256": _file_hash(groups_path),
        "lineage_assignments": dict(sorted(assignments.items())),
        "source_group_assignments": dict(sorted(group_assignments.items())),
        "partition_lineage_counts": dict(sorted(counts.items())),
        "class_partition_lineage_counts": class_partition_counts,
        "class_real_lineage_counts": {
            label: len(values) for label, values in sorted(by_label.items())
        },
        "declared_model_classes": frozen_classes,
        "class_declaration_source": declaration_source,
        "unsupported_lockbox_classes": unsupported,
        "synthetic_policy": "training only; never calibration or lockbox",
        "partition_roles": {
            "real_train": "model fitting and development",
            "real_calibration": "real-only probability calibration and thresholds",
            "real_lockbox": "one-time development selection; not final confirmation",
            "real_unassigned": "insufficient class support; excluded from model work",
        },
        "confirmation_policy": (
            "A separately controlled, never-opened real confirmation cohort is required "
            "for an accuracy or release claim."
        ),
    }
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(destination)
    return payload


def load_and_validate_ledger(
    path: str | Path,
    labels_csv: str | Path,
    groups_csv: str | Path,
) -> dict[str, Any]:
    loaded = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("split ledger root must be an object")
    ledger = cast(dict[str, Any], loaded)
    if ledger.get("schema") != SPLIT_SCHEMA or ledger.get("frozen") is not True:
        raise ValueError("split ledger is unsupported or not frozen")
    if ledger.get("labels_sha256") != _file_hash(Path(labels_csv)):
        raise ValueError("split ledger labels hash differs from the dataset")
    if ledger.get("groups_sha256") != _file_hash(Path(groups_csv)):
        raise ValueError("split ledger groups hash differs from the dataset")
    assignments = ledger.get("source_group_assignments")
    if not isinstance(assignments, dict) or not assignments:
        raise ValueError("split ledger has no real source-group assignments")
    allowed = {
        "real_train",
        "real_calibration",
        "real_lockbox",
        "real_unassigned",
    }
    if set(assignments.values()) - allowed:
        raise ValueError("split ledger contains an unknown partition")
    declared = ledger.get("declared_model_classes")
    if (
        not isinstance(declared, list)
        or not declared
        or not all(isinstance(value, str) and value for value in declared)
    ):
        raise ValueError("split ledger has no frozen declared model classes")
    lineage_assignments = ledger.get("lineage_assignments")
    if not isinstance(lineage_assignments, dict) or not lineage_assignments:
        raise ValueError("split ledger has no real lineage assignments")
    groups = pd.read_csv(groups_csv)
    source_types = require_known_source_types(groups)
    source_groups = effective_group_values(groups)
    if "lineage_root_id" not in groups.columns:
        raise ValueError("groups CSV lacks lineage_root_id")
    lineages = groups["lineage_root_id"].fillna("").astype(str).str.strip().to_numpy()
    observed_real_groups: set[str] = set()
    observed_real_lineages: set[str] = set()
    for group, lineage, source_type in zip(source_groups, lineages, source_types):
        if source_type != "real":
            if str(group) in assignments:
                raise ValueError("split ledger assigns a non-real source group")
            continue
        observed_real_groups.add(str(group))
        observed_real_lineages.add(str(lineage))
        if assignments.get(str(group)) != lineage_assignments.get(str(lineage)):
            raise ValueError(
                "split ledger source-group and lineage assignments disagree"
            )
    if set(assignments) != observed_real_groups:
        raise ValueError("split ledger does not cover exactly the real source groups")
    if set(lineage_assignments) != observed_real_lineages:
        raise ValueError("split ledger does not cover exactly the real lineages")
    return ledger
