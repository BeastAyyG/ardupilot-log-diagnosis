"""Hyperparameter search scored on deployed incident units, never correlated rows."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import numpy as np
from sklearn.base import clone
from sklearn.model_selection import ParameterGrid, StratifiedGroupKFold
from sklearn.pipeline import Pipeline

from synthetic_data.ablation_core import (
    LINEAGE_WEIGHTING_CONTRACT,
    aggregate_real_lineages,
    training_weights,
)
from synthetic_data.evaluation_metrics import incident_metrics
from synthetic_data.schema import canonical_json_bytes, sha256_bytes

CV_PARTITION_CONTRACT = "unique_group_class_stratified/v1"
EXACT_DUPLICATE_CONTRACT = "exact_feature_target_evaluation_unit_collapse/v1"
SEARCH_DESIGN_SCHEMA = "logdiagnosis.lineage-budgeted-xgb-search/v1"


def build_search_design(independent_training_lineages: int) -> dict[str, Any]:
    """Preregister search breadth in proportion to independent evidence."""

    if (
        not isinstance(independent_training_lineages, int)
        or isinstance(independent_training_lineages, bool)
        or independent_training_lineages < 4
    ):
        raise ValueError("search design requires at least four training lineages")
    if independent_training_lineages < 16:
        tier = "conservative_4"
        depth = [3]
        estimators = [100]
        subsample = [1.0]
        columns = [1.0]
    elif independent_training_lineages < 64:
        tier = "moderate_16"
        depth = [3, 5]
        estimators = [100, 200]
        subsample = [1.0]
        columns = [1.0]
    else:
        tier = "full_64"
        depth = [3, 5]
        estimators = [100, 200]
        subsample = [0.8, 1.0]
        columns = [0.8, 1.0]
    parameter_grid = {
        "model__max_depth": depth,
        "model__learning_rate": [0.05, 0.1],
        "model__n_estimators": estimators,
        "model__min_child_weight": [1, 3],
        "model__subsample": subsample,
        "model__colsample_bytree": columns,
    }
    candidate_count = int(
        np.prod([len(values) for values in parameter_grid.values()])
    )
    return {
        "schema": SEARCH_DESIGN_SCHEMA,
        "tier": tier,
        "independent_training_lineages": independent_training_lineages,
        "candidate_count": candidate_count,
        "parameter_grid": parameter_grid,
        "selection_metric": "mean_deployed_incident_macro_f1",
        "selection_unit": "evaluation_unit",
        "multiple_comparison_budget_rule": "4_if_lt16__16_if_lt64__else64",
    }


def search_design_sha256(design: dict[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes(design))


def validate_training_design(
    evaluation: Mapping[str, Any],
    independent_training_lineages: int,
) -> tuple[dict[str, str], dict[str, Any], str]:
    """Recompute artifact-bound fold, weighting, and search contracts."""

    contracts = {
        "cv_partition_contract": CV_PARTITION_CONTRACT,
        "exact_duplicate_contract": EXACT_DUPLICATE_CONTRACT,
        "training_weighting_contract": LINEAGE_WEIGHTING_CONTRACT,
    }
    for field, expected in contracts.items():
        if evaluation.get(field) != expected:
            raise ValueError(f"Artifact training contract mismatch for {field}.")
    design = build_search_design(independent_training_lineages)
    design_hash = search_design_sha256(design)
    if (
        evaluation.get("hyperparameter_search_design") != design
        or evaluation.get("hyperparameter_search_design_sha256") != design_hash
    ):
        raise ValueError("Artifact hyperparameter search design mismatch.")
    return contracts, design, design_hash


def build_grouped_folds(
    target: np.ndarray,
    fold_units: np.ndarray,
    *,
    n_splits: int,
    seed: int = 42,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Build row folds from one representative per group/class combination."""

    target = np.asarray(target)
    fold_units = np.asarray(fold_units)
    if len(target) != len(fold_units) or not len(target):
        raise ValueError("fold targets and units must be non-empty and row-aligned")
    if n_splits < 2:
        raise ValueError("grouped search requires at least two folds")
    pairs = sorted({(str(unit), int(label)) for unit, label in zip(fold_units, target)})
    pair_units = np.asarray([unit for unit, _ in pairs])
    pair_target = np.asarray([label for _, label in pairs], dtype=int)
    splitter = StratifiedGroupKFold(
        n_splits=n_splits,
        shuffle=True,
        random_state=seed,
    )
    folds: list[tuple[np.ndarray, np.ndarray]] = []
    for fit_pairs, score_pairs in splitter.split(
        np.zeros(len(pairs)), pair_target, pair_units
    ):
        fit_units = set(pair_units[fit_pairs].tolist())
        score_units = set(pair_units[score_pairs].tolist())
        if not fit_units.isdisjoint(score_units):
            raise AssertionError("grouped CV assigned one unit to both fold sides")
        fit_indices = np.flatnonzero(
            np.asarray([str(unit) in fit_units for unit in fold_units])
        )
        score_indices = np.flatnonzero(
            np.asarray([str(unit) in score_units for unit in fold_units])
        )
        if not len(fit_indices) or not len(score_indices):
            raise ValueError("grouped CV produced an empty fold side")
        folds.append((fit_indices, score_indices))
    return folds


def _row_key(
    matrix: np.ndarray,
    target: np.ndarray,
    evaluation_units: np.ndarray,
    index: int,
) -> tuple[str, int, bytes]:
    row = np.asarray(matrix[index], dtype=np.float64).copy()
    row[row == 0.0] = 0.0
    return str(evaluation_units[index]), int(target[index]), row.tobytes()


def _unique_indices(
    matrix: np.ndarray,
    target: np.ndarray,
    evaluation_units: np.ndarray,
    indices: np.ndarray,
) -> np.ndarray:
    seen: set[tuple[str, int, bytes]] = set()
    selected: list[int] = []
    for raw_index in indices:
        index = int(raw_index)
        key = _row_key(matrix, target, evaluation_units, index)
        if key not in seen:
            seen.add(key)
            selected.append(index)
    return np.asarray(selected, dtype=int)


def _collapsed_fit_rows(
    matrix: np.ndarray,
    target: np.ndarray,
    evaluation_units: np.ndarray,
    weight_groups: np.ndarray,
    weight_lineages: np.ndarray,
    indices: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    selected = _unique_indices(matrix, target, evaluation_units, indices)
    weights = training_weights(
        target[selected],
        weight_groups[selected],
        weight_lineages[selected],
    )
    return selected, weights


def fit_grouped_search(
    pipeline: Pipeline,
    parameter_grid: dict[str, list[Any]],
    matrix: np.ndarray,
    target: np.ndarray,
    evaluation_units: np.ndarray,
    weight_groups: np.ndarray,
    weight_lineages: np.ndarray,
    folds: Iterable[tuple[np.ndarray, np.ndarray]],
    classes: list[str],
) -> tuple[Pipeline, dict[str, Any], float]:
    """Select and refit a pipeline using max-window incident Macro-F1."""

    matrix = np.asarray(matrix, dtype=float)
    target = np.asarray(target)
    evaluation_units = np.asarray(evaluation_units)
    weight_groups = np.asarray(weight_groups)
    weight_lineages = np.asarray(weight_lineages)
    row_count = len(matrix)
    if not (
        row_count
        and len(target) == row_count
        and len(evaluation_units) == row_count
        and len(weight_groups) == row_count
        and len(weight_lineages) == row_count
    ):
        raise ValueError("grouped search inputs must be non-empty and row-aligned")
    if not np.isfinite(matrix).all():
        raise ValueError("grouped search features must be finite")
    if len(classes) < 2 or len(classes) != len(set(classes)):
        raise ValueError("grouped search classes must be unique")
    unit_targets: dict[str, set[int]] = {}
    for unit, label in zip(evaluation_units, target):
        unit_targets.setdefault(str(unit), set()).add(int(label))
    if any(len(values) != 1 for values in unit_targets.values()):
        raise ValueError("grouped search evaluation units have mixed targets")

    best_score = -np.inf
    best_parameters: dict[str, Any] | None = None
    fold_list: list[tuple[np.ndarray, np.ndarray]] = []
    required_targets = set(range(len(classes)))
    for raw_fit, raw_score in folds:
        fit_indices = np.asarray(raw_fit, dtype=int)
        score_indices = np.asarray(raw_score, dtype=int)
        if not len(fit_indices) or not len(score_indices):
            raise ValueError("grouped search fold sides cannot be empty")
        if (
            np.any(fit_indices < 0)
            or np.any(score_indices < 0)
            or np.any(fit_indices >= row_count)
            or np.any(score_indices >= row_count)
        ):
            raise ValueError("grouped search fold index is outside the dataset")
        fit_units = set(evaluation_units[fit_indices].tolist())
        score_units = set(evaluation_units[score_indices].tolist())
        if not fit_units.isdisjoint(score_units):
            raise ValueError("grouped search evaluation units cross fold sides")
        if set(target[fit_indices].tolist()) != required_targets:
            raise ValueError("grouped search fit fold lacks a declared class")
        fold_list.append((fit_indices, score_indices))
    if not fold_list:
        raise ValueError("grouped search requires at least one fold")
    for parameters in ParameterGrid(parameter_grid):
        scores: list[float] = []
        for fit_indices, score_indices in fold_list:
            fit_indices, fit_weights = _collapsed_fit_rows(
                matrix,
                target,
                evaluation_units,
                weight_groups,
                weight_lineages,
                np.asarray(fit_indices, dtype=int),
            )
            score_indices = _unique_indices(
                matrix,
                target,
                evaluation_units,
                np.asarray(score_indices, dtype=int),
            )
            candidate = clone(pipeline).set_params(**parameters)
            candidate.fit(
                matrix[fit_indices],
                target[fit_indices],
                model__sample_weight=fit_weights,
            )
            probabilities = candidate.predict_proba(matrix[score_indices])
            _, grouped_target, grouped_probabilities = aggregate_real_lineages(
                probabilities,
                target[score_indices],
                evaluation_units[score_indices],
            )
            scores.append(
                incident_metrics(grouped_target, grouped_probabilities, classes)[
                    "macro_f1"
                ]
            )
        score = float(np.mean(scores))
        if score > best_score:
            best_score = score
            best_parameters = dict(parameters)
    if best_parameters is None:
        raise ValueError("Grouped hyperparameter search produced no candidates.")
    fit_indices, fit_weights = _collapsed_fit_rows(
        matrix,
        target,
        evaluation_units,
        weight_groups,
        weight_lineages,
        np.arange(row_count),
    )
    fitted = clone(pipeline).set_params(**best_parameters)
    fitted.fit(
        matrix[fit_indices],
        target[fit_indices],
        model__sample_weight=fit_weights,
    )
    return fitted, best_parameters, best_score
