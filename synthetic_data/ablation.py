"""Development-only synthetic dose screens on frozen real partitions."""

from __future__ import annotations

import hashlib
import json
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

from .ablation_core import fit_arm, stratified_paired_bootstrap
from .ablation_ledger import write_prediction_ledger
from .schema import sha256_file
from .splits import load_and_validate_ledger

ABLATION_SCHEMA = "logdiagnosis.synthetic-augmentation-ablation/v2"
MODEL_SEEDS = (1, 7, 21, 42, 99)
SYNTHETIC_TYPES = {"sitl", "hil", "simulation"}


def _stable_rank(seed: int, value: str) -> str:
    return hashlib.sha256(f"{seed}:{value}".encode()).hexdigest()


def _primary_labels(labels: pd.DataFrame, groups: pd.DataFrame) -> np.ndarray:
    output: list[str] = []
    allowed = labels.columns.tolist()
    for position, (_, row) in enumerate(labels.iterrows()):
        preferred = (
            groups.iloc[position].get("primary_label", "")
            if "primary_label" in groups
            else ""
        )
        output.append(primary_label_for_row(row, preferred=preferred, allowed=allowed))
    return np.asarray(output)


def _required_text_column(frame: pd.DataFrame, name: str) -> np.ndarray:
    if name not in frame.columns:
        raise ValueError(f"groups CSV lacks required provenance column {name}")
    values = frame[name].fillna("").astype(str).str.strip().to_numpy()
    if any(not value for value in values):
        raise ValueError(f"groups CSV contains blank {name} values")
    return values


def _optional_text_column(frame: pd.DataFrame, name: str) -> np.ndarray:
    if name not in frame.columns:
        return np.asarray([""] * len(frame))
    return frame[name].fillna("").astype(str).str.strip().to_numpy()


def _check_synthetic_provenance(
    groups_frame: pd.DataFrame,
    synthetic_mask: np.ndarray,
    real_train_mask: np.ndarray,
    protected_real_mask: np.ndarray,
    lineages: np.ndarray,
) -> dict[str, Any]:
    if not synthetic_mask.any():
        return {
            "complete": True,
            "conditioning_lineage_column_present": True,
            "near_duplicate_cluster_column_present": True,
        }
    required = (
        "manifest_sha256",
        "parameter_schema_sha256",
        "artifact_sha256",
        "run_fingerprint",
        "manifestation_predicate_sha256",
    )
    for column in required:
        values = _optional_text_column(groups_frame, column)
        if np.any(values[synthetic_mask] == ""):
            raise ValueError(f"verified synthetic rows contain blank {column}")

    conditioning = _optional_text_column(groups_frame, "conditioning_real_lineage_id")
    if "conditioning_real_lineage_id" not in groups_frame.columns:
        raise ValueError("verified synthetic rows lack conditioning lineage provenance")
    modes = _optional_text_column(groups_frame, "conditioning_mode")
    allowed_modes = {"pure_simulation", "real_conditioned"}
    if any(value not in allowed_modes for value in modes[synthetic_mask]):
        raise ValueError(
            "verified synthetic rows require pure_simulation or real_conditioned mode"
        )
    pure = synthetic_mask & (modes == "pure_simulation")
    conditioned = synthetic_mask & (modes == "real_conditioned")
    if np.any(conditioning[pure] != ""):
        raise ValueError("pure-simulation rows cannot claim a conditioning lineage")
    real_train_lineages = set(lineages[real_train_mask].tolist())
    if any(
        not value or value not in real_train_lineages
        for value in conditioning[conditioned]
    ):
        raise ValueError(
            "real-conditioned synthetic rows must name a real-training lineage"
        )
    protected = set(lineages[protected_real_mask].tolist())
    descendants = {value for value in conditioning[synthetic_mask] if value}
    overlap = sorted(protected & descendants)
    if overlap:
        raise ValueError(
            "synthetic descendants originate from calibration/development-test lineages: "
            + ", ".join(overlap[:10])
        )

    payloads = _required_text_column(groups_frame, "sha256")
    exact_overlap = sorted(
        set(payloads[synthetic_mask].tolist())
        & set(payloads[protected_real_mask].tolist())
    )
    if exact_overlap:
        raise ValueError("synthetic and protected real partitions share payload hashes")

    cluster_column = "near_duplicate_cluster_id"
    clusters = _optional_text_column(groups_frame, cluster_column)
    synthetic_clusters = {value for value in clusters[synthetic_mask] if value}
    protected_clusters = {value for value in clusters[protected_real_mask] if value}
    cluster_overlap = sorted(synthetic_clusters & protected_clusters)
    if cluster_overlap:
        raise ValueError(
            "synthetic and protected real rows share near-duplicate clusters"
        )
    return {
        "complete": bool(np.all(clusters[synthetic_mask] != "")),
        "conditioning_lineage_column_present": True,
        "conditioning_mode_complete": True,
        "near_duplicate_cluster_column_present": cluster_column in groups_frame,
        "near_duplicate_clusters_complete": bool(
            np.all(clusters[synthetic_mask] != "")
        ),
    }


def _class_stratified_lineage_selection(
    intervention_labels: dict[str, str],
    real_train_indices: np.ndarray,
    primary: np.ndarray,
    lineages: np.ndarray,
    classes: list[str],
    ratio: float,
    *,
    seed: int,
) -> set[str]:
    selected: set[str] = set()
    for label in classes:
        if label == "healthy":
            continue
        train_labels = primary[real_train_indices]
        train_lineages = lineages[real_train_indices]
        real_count = len(set(train_lineages[train_labels == label]))
        candidates = sorted(
            [
                lineage
                for lineage, intervention_label in intervention_labels.items()
                if intervention_label == label
            ],
            key=lambda value: _stable_rank(seed, f"{label}:{value}"),
        )
        desired = min(
            len(candidates),
            max(1, round(ratio * real_count)) if real_count else 0,
        )
        selected.update(candidates[:desired])
    return selected


def _paired_intervention_labels(
    groups: pd.DataFrame,
    synthetic_mask: np.ndarray,
    primary: np.ndarray,
    lineages: np.ndarray,
) -> dict[str, str]:
    roles = _optional_text_column(groups, "pair_role")
    mapping: dict[str, str] = {}
    for lineage in sorted(set(lineages[synthetic_mask].tolist())):
        positions = np.flatnonzero(synthetic_mask & (lineages == lineage))
        role_set = set(roles[positions].tolist())
        intervention_labels = set(
            primary[positions][roles[positions] == "intervention"].tolist()
        )
        control_labels = set(
            primary[positions][roles[positions] == "sham_control"].tolist()
        )
        if (
            role_set != {"sham_control", "intervention"}
            or len(intervention_labels) != 1
            or control_labels != {"healthy"}
        ):
            raise ValueError(
                "verified synthetic fault lineages must contain one reciprocal "
                "healthy sham/intervention pair"
            )
        mapping[lineage] = next(iter(intervention_labels))
    return mapping


def run_ablation(
    features_csv: str | Path,
    labels_csv: str | Path,
    groups_csv: str | Path,
    split_ledger: str | Path,
    *,
    output_path: str | Path | None = None,
    prediction_ledger_path: str | Path | None = None,
    synthetic_ratios: tuple[float, ...] = (0.10, 0.25, 0.50, 1.0, 2.0),
    bootstrap_draws: int = 10000,
    model_seeds: tuple[int, ...] = MODEL_SEEDS,
) -> dict[str, Any]:
    """Screen doses for development; never produce a final accuracy claim."""

    features_path, labels_path, groups_path = map(
        Path, (features_csv, labels_csv, groups_csv)
    )
    features = pd.read_csv(features_path)
    labels = pd.read_csv(labels_path)
    groups_frame = pd.read_csv(groups_path)
    if not (len(features) == len(labels) == len(groups_frame)):
        raise ValueError("dataset triplet row counts differ")
    if features.columns.tolist() != FEATURE_NAMES:
        raise ValueError("feature CSV does not match the runtime feature schema")
    matrix = features.to_numpy(dtype=float)
    if not np.isfinite(matrix).all():
        raise ValueError("feature matrix contains non-finite values")
    if bootstrap_draws < 1 or not model_seeds:
        raise ValueError("bootstrap_draws and model_seeds must be non-empty")

    source_types = require_known_source_types(groups_frame)
    source_groups = effective_group_values(groups_frame)
    lineages = _required_text_column(groups_frame, "lineage_root_id")
    primary = _primary_labels(labels, groups_frame)
    ledger = load_and_validate_ledger(split_ledger, labels_path, groups_path)
    assignments = ledger["source_group_assignments"]
    classes = list(ledger["declared_model_classes"])
    class_id = {name: index for index, name in enumerate(classes)}
    target = np.asarray([class_id.get(label, -1) for label in primary], dtype=int)
    supported = target >= 0

    def real_partition(name: str) -> np.ndarray:
        return np.asarray(
            [
                source_type == "real" and assignments.get(str(group)) == name
                for group, source_type in zip(source_groups, source_types)
            ]
        )

    real_train_mask = real_partition("real_train")
    calibration_mask = real_partition("real_calibration")
    development_test_mask = real_partition("real_lockbox")
    real_train_indices = np.flatnonzero(real_train_mask & supported)
    calibration_indices = np.flatnonzero(calibration_mask & supported)
    test_indices = np.flatnonzero(development_test_mask & supported)
    missing_train = sorted(set(classes) - set(primary[real_train_mask].tolist()))
    if missing_train:
        raise ValueError(
            "declared classes lack real training support: " + ", ".join(missing_train)
        )
    if not len(test_indices):
        raise ValueError("development test partition has no declared-class rows")

    verification = _optional_text_column(groups_frame, "verification_status")
    synthetic_mask = (
        np.isin(source_types, list(SYNTHETIC_TYPES))
        & (verification == "accepted")
        & supported
    )
    provenance = _check_synthetic_provenance(
        groups_frame,
        synthetic_mask,
        real_train_mask,
        calibration_mask | development_test_mask,
        lineages,
    )
    intervention_labels = _paired_intervention_labels(
        groups_frame, synthetic_mask, primary, lineages
    )

    baseline_metrics, baseline_predictions = fit_arm(
        matrix,
        target,
        source_groups,
        lineages,
        real_train_indices,
        calibration_indices,
        test_indices,
        classes,
        model_seeds=model_seeds,
    )
    arms: list[dict[str, Any]] = [
        {
            "name": "real_only",
            "synthetic_ratio": 0.0,
            "synthetic_lineages": 0,
            "metrics": baseline_metrics,
        }
    ]
    prediction_arms: list[tuple[str, dict[str, Any]]] = [
        ("real_only", baseline_predictions)
    ]
    for ratio in synthetic_ratios:
        if ratio <= 0:
            raise ValueError("synthetic ratios must be positive")
        selected = _class_stratified_lineage_selection(
            intervention_labels,
            real_train_indices,
            primary,
            lineages,
            classes,
            float(ratio),
            seed=20260823,
        )
        selected_indices = np.flatnonzero(
            synthetic_mask & np.isin(lineages, list(selected))
        )
        if not len(selected_indices):
            continue
        training_indices = np.sort(
            np.concatenate((real_train_indices, selected_indices))
        )
        metrics, predictions = fit_arm(
            matrix,
            target,
            source_groups,
            lineages,
            training_indices,
            calibration_indices,
            test_indices,
            classes,
            model_seeds=model_seeds,
        )
        interval = stratified_paired_bootstrap(
            baseline_predictions,
            predictions,
            len(classes),
            draws=bootstrap_draws,
        )
        recall_losses = {
            label: baseline_metrics["per_class_recall"][label]
            - metrics["per_class_recall"][label]
            for label in classes
        }
        baseline_alarm = baseline_metrics["healthy_false_alarm_rate"]
        candidate_alarm = metrics["healthy_false_alarm_rate"]
        exploratory_screen = bool(
            interval["lower_95"] > 0
            and baseline_alarm is not None
            and candidate_alarm is not None
            and candidate_alarm <= baseline_alarm + 0.01
            and metrics["top_label_incident_ece"] <= 0.08
            and max(recall_losses.values(), default=0.0) <= 0.05
            and provenance["complete"]
        )
        class_counts: dict[str, int] = defaultdict(int)
        for root in selected:
            class_counts[intervention_labels[root]] += 1
        arm_name = f"real_plus_verified_sitl_{ratio:g}x"
        arms.append(
            {
                "name": arm_name,
                "synthetic_ratio": float(ratio),
                "synthetic_lineages": int(len(selected)),
                "synthetic_control_lineages": int(len(selected)),
                "synthetic_intervention_lineages_by_class": dict(
                    sorted(class_counts.items())
                ),
                "metrics": metrics,
                "paired_bootstrap": interval,
                "maximum_per_class_recall_loss": max(
                    recall_losses.values(), default=0.0
                ),
                "exploratory_retention_screen_pass": exploratory_screen,
            }
        )
        prediction_arms.append((arm_name, predictions))

    out_of_task = sorted(
        set(primary[development_test_mask].tolist()) - set(classes) - {""}
    )
    dataset_binding = {
        "features_sha256": sha256_file(features_path),
        "labels_sha256": sha256_file(labels_path),
        "groups_sha256": sha256_file(groups_path),
        "split_ledger_sha256": sha256_file(split_ledger),
    }
    ledger_destination = (
        Path(prediction_ledger_path)
        if prediction_ledger_path is not None
        else (
            Path(output_path).with_suffix(".predictions.json")
            if output_path is not None
            else None
        )
    )
    prediction_ledger_sha256 = (
        write_prediction_ledger(
            ledger_destination,
            dataset=dataset_binding,
            classes=classes,
            model_seeds=model_seeds,
            arms=prediction_arms,
        )
        if ledger_destination is not None
        else None
    )
    report = {
        "schema": ABLATION_SCHEMA,
        "non_promoting": True,
        "evaluation_role": "development_dose_screen",
        "confirmation_required": True,
        "development_test_consumed": True,
        "development_test_usable_for_confirmation": False,
        "dataset": dataset_binding,
        "prediction_ledger_sha256": prediction_ledger_sha256,
        "prediction_ledger_file": (
            ledger_destination.name if ledger_destination is not None else None
        ),
        "declared_classes": classes,
        "out_of_task_development_labels": out_of_task,
        "real_only_scoring": True,
        "synthetic_calibration_rows": 0,
        "synthetic_development_test_rows": 0,
        "synthetic_provenance": provenance,
        "verified_synthetic_lineages_available": int(
            len(set(lineages[synthetic_mask].tolist()))
        ),
        "status": (
            "measured_development_only"
            if synthetic_mask.any()
            else "blocked_no_verified_synthetic_data"
        ),
        "arms": arms,
        "selection_warning": (
            "Multiple doses reuse an opened development partition. Choose and freeze one "
            "candidate before a new, blinded real confirmation cohort."
        ),
        "accuracy_claim": "not_demonstrated",
        "release_gate_pass": False,
    }
    if output_path:
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report
