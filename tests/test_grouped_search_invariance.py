from __future__ import annotations

import numpy as np
import pytest
from sklearn.feature_selection import SelectKBest, f_classif
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from synthetic_data.ablation_core import training_weights
from training.grouped_search import (
    build_grouped_folds,
    build_search_design,
    fit_grouped_search,
    search_design_sha256,
)


def _data() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    matrix: list[list[float]] = []
    target: list[int] = []
    units: list[str] = []
    values = {
        0: [(-2.0, 0.1), (-0.7, 0.8), (-0.2, -0.5), (0.4, 0.1)],
        1: [(-0.4, 0.3), (0.1, -0.6), (0.8, 0.7), (2.0, -0.2)],
    }
    for class_id, centers in values.items():
        for unit_index, (first, second) in enumerate(centers):
            unit = f"class-{class_id}-unit-{unit_index}"
            for offset in (-0.08, 0.08):
                matrix.append([first + offset, second - offset])
                target.append(class_id)
                units.append(unit)
    return np.asarray(matrix), np.asarray(target), np.asarray(units)


def _pipeline() -> Pipeline:
    return Pipeline(
        [
            ("select", SelectKBest(score_func=f_classif, k=1)),
            ("scale", StandardScaler()),
            (
                "model",
                LogisticRegression(random_state=42, solver="liblinear"),
            ),
        ]
    )


def _fold_units(
    folds: list[tuple[np.ndarray, np.ndarray]], units: np.ndarray
) -> list[tuple[set[str], set[str]]]:
    return [
        (set(units[fit].tolist()), set(units[score].tolist()))
        for fit, score in folds
    ]


def _unit_weight_totals(weights: np.ndarray, units: np.ndarray) -> dict[str, float]:
    return {
        unit: float(weights[units == unit].sum()) for unit in sorted(set(units))
    }


def test_exact_window_duplication_cannot_change_grouped_model_selection() -> None:
    matrix, target, units = _data()
    weight_groups = np.asarray(
        [f"{unit}:attachment:{index % 2}" for index, unit in enumerate(units)]
    )
    folds = build_grouped_folds(target, units, n_splits=2, seed=11)
    weights = training_weights(target, weight_groups, units)
    fitted, parameters, score = fit_grouped_search(
        _pipeline(),
        {"model__C": [0.03, 0.3, 3.0]},
        matrix,
        target,
        units,
        weight_groups,
        units,
        folds,
        ["zero", "one"],
    )

    copied = np.repeat(np.asarray([0]), 25)
    duplicated_matrix = np.concatenate([matrix, matrix[copied]])
    duplicated_target = np.concatenate([target, target[copied]])
    duplicated_units = np.concatenate([units, units[copied]])
    duplicated_weight_groups = np.concatenate([weight_groups, weight_groups[copied]])
    duplicated_folds = build_grouped_folds(
        duplicated_target, duplicated_units, n_splits=2, seed=11
    )
    duplicated_weights = training_weights(
        duplicated_target, duplicated_weight_groups, duplicated_units
    )
    duplicated_fitted, duplicated_parameters, duplicated_score = fit_grouped_search(
        _pipeline(),
        {"model__C": [0.03, 0.3, 3.0]},
        duplicated_matrix,
        duplicated_target,
        duplicated_units,
        duplicated_weight_groups,
        duplicated_units,
        duplicated_folds,
        ["zero", "one"],
    )

    assert _fold_units(folds, units) == _fold_units(
        duplicated_folds, duplicated_units
    )
    assert _unit_weight_totals(weights, units) == pytest.approx(
        _unit_weight_totals(duplicated_weights, duplicated_units)
    )
    assert float(weights.sum()) == pytest.approx(len(set(units)))
    assert float(duplicated_weights.sum()) == pytest.approx(len(set(units)))
    assert duplicated_parameters == parameters
    assert duplicated_score == pytest.approx(score)
    probe = np.asarray([[-0.5, 0.2], [0.0, 0.0], [0.5, -0.2]])
    assert duplicated_fitted.predict_proba(probe) == pytest.approx(
        fitted.predict_proba(probe)
    )


def test_grouped_search_rejects_mixed_target_evaluation_units() -> None:
    matrix, target, units = _data()
    units[8] = units[0]
    folds = build_grouped_folds(target, np.arange(len(target)), n_splits=2)
    with pytest.raises(ValueError, match="evaluation units have mixed targets"):
        fit_grouped_search(
            _pipeline(),
            {"model__C": [1.0]},
            matrix,
            target,
            units,
            units,
            units,
            folds,
            ["zero", "one"],
        )


def test_search_breadth_is_deterministically_budgeted_by_independent_lineages() -> None:
    sparse = build_search_design(4)
    medium = build_search_design(16)
    large = build_search_design(64)

    assert (sparse["tier"], sparse["candidate_count"]) == ("conservative_4", 4)
    assert (medium["tier"], medium["candidate_count"]) == ("moderate_16", 16)
    assert (large["tier"], large["candidate_count"]) == ("full_64", 64)
    assert search_design_sha256(sparse) == search_design_sha256(
        build_search_design(4)
    )
    assert len({search_design_sha256(item) for item in (sparse, medium, large)}) == 3
    with pytest.raises(ValueError, match="at least four"):
        build_search_design(3)
