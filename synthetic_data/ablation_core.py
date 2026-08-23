"""Lineage-aware fitting and paired resampling for augmentation studies."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

import numpy as np
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.metrics import f1_score

from .evaluation_metrics import (
    RealOnlyCalibrator,
    calibration_method_config_sha256,
    incident_metrics,
)

LINEAGE_WEIGHTING_CONTRACT = (
    "inverse_window_group_lineage_class_normalized_to_unique_lineages/v2"
)


def training_weights(
    target: np.ndarray,
    source_groups: np.ndarray,
    lineages: np.ndarray,
) -> np.ndarray:
    """Give each independent lineage bounded influence despite many windows/arms."""

    target = np.asarray(target)
    source_groups = np.asarray(source_groups)
    lineages = np.asarray(lineages)
    if not (len(target) == len(source_groups) == len(lineages)) or not len(target):
        raise ValueError("training weight inputs must be non-empty and row-aligned")
    if any(not str(value).strip() for value in source_groups) or any(
        not str(value).strip() for value in lineages
    ):
        raise ValueError("training weight groups and lineages cannot be blank")

    group_counts = Counter(source_groups.tolist())
    group_targets: dict[str, int] = {}
    group_lineages: dict[str, str] = {}
    for group in set(source_groups.tolist()):
        indices = np.flatnonzero(source_groups == group)
        labels = set(target[indices].tolist())
        roots = set(lineages[indices].tolist())
        if len(labels) != 1 or len(roots) != 1:
            raise ValueError(f"source group {group} has mixed targets or lineages")
        group_targets[str(group)] = int(next(iter(labels)))
        group_lineages[str(group)] = str(next(iter(roots)))

    lineage_groups: dict[str, set[str]] = defaultdict(set)
    class_lineages: dict[int, set[str]] = defaultdict(set)
    for group, label in group_targets.items():
        root = group_lineages[group]
        lineage_groups[root].add(group)
        class_lineages[label].add(root)

    weights = np.asarray(
        [
            1.0
            / group_counts[str(group)]
            / len(lineage_groups[str(root)])
            / len(class_lineages[int(label)])
            for group, root, label in zip(source_groups, lineages, target)
        ],
        dtype=float,
    )
    # Keep total fitting mass tied to independent units. Scaling to row count
    # would change XGBoost regularization and min_child_weight when one window
    # is copied, even though its lineage evidence did not change.
    weights *= len(set(lineages.tolist())) / weights.sum()
    return weights


def aggregate_real_lineages(
    probabilities: np.ndarray,
    target: np.ndarray,
    lineages: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Collapse correlated windows and attachments to independent real lineages."""

    names: list[str] = []
    targets: list[int] = []
    scores_by_lineage: list[np.ndarray] = []
    for lineage in sorted(set(lineages.tolist())):
        indices = np.flatnonzero(lineages == lineage)
        values = set(target[indices].tolist())
        if len(values) != 1:
            raise ValueError(f"real lineage {lineage} has multiple target labels")
        # Runtime MLClassifier.predict_windows uses the independent per-class
        # maxima directly; it does not renormalize them into a simplex.
        scores = np.max(probabilities[indices], axis=0)
        names.append(str(lineage))
        targets.append(int(next(iter(values))))
        scores_by_lineage.append(scores)
    return (
        np.asarray(names),
        np.asarray(targets, dtype=int),
        np.asarray(scores_by_lineage, dtype=float),
    )


def fit_arm(
    matrix: np.ndarray,
    target: np.ndarray,
    source_groups: np.ndarray,
    lineages: np.ndarray,
    train_indices: np.ndarray,
    calibration_indices: np.ndarray,
    test_indices: np.ndarray,
    classes: list[str],
    *,
    model_seeds: tuple[int, ...],
) -> tuple[dict[str, Any], dict[str, Any]]:
    test_sum = np.zeros((len(test_indices), len(classes)), dtype=float)
    calibration_sum = np.zeros((len(calibration_indices), len(classes)), dtype=float)
    weights = training_weights(
        target[train_indices],
        source_groups[train_indices],
        lineages[train_indices],
    )
    for seed in model_seeds:
        estimator = ExtraTreesClassifier(
            n_estimators=200,
            min_samples_leaf=2,
            max_features="sqrt",
            class_weight="balanced",
            n_jobs=-1,
            random_state=seed,
        )
        estimator.fit(
            matrix[train_indices], target[train_indices], sample_weight=weights
        )
        for indices, accumulator in (
            (test_indices, test_sum),
            (calibration_indices, calibration_sum),
        ):
            if not len(indices):
                continue
            raw = estimator.predict_proba(matrix[indices])
            accumulator[:, np.asarray(estimator.classes_, dtype=int)] += raw

    test_window_probabilities = test_sum / len(model_seeds)
    test_lineages, test_target, test_probabilities = aggregate_real_lineages(
        test_window_probabilities,
        target[test_indices],
        lineages[test_indices],
    )
    calibrator = RealOnlyCalibrator(len(classes))
    if len(calibration_indices):
        calibration_window_probabilities = calibration_sum / len(model_seeds)
        _, calibration_target, calibration_probabilities = aggregate_real_lineages(
            calibration_window_probabilities,
            target[calibration_indices],
            lineages[calibration_indices],
        )
        calibrator.fit(calibration_probabilities, calibration_target)
    test_probabilities = calibrator.transform(test_probabilities)
    result = incident_metrics(test_target, test_probabilities, classes)
    calibration_support = calibrator.support_by_class(classes)
    result.update(
        {
            "training_rows": int(len(train_indices)),
            "training_lineages": int(len(set(lineages[train_indices].tolist()))),
            "calibration_lineages": int(
                len(set(lineages[calibration_indices].tolist()))
            ),
            "development_test_lineages": int(len(test_lineages)),
            "calibrated_classes": calibrator.calibrated_class_count,
            "calibration_per_class_real_lineages": calibration_support,
            "per_class_real_calibration_lineages": {
                name: int(item["positive_real_lineages"])
                for name, item in calibration_support.items()
            },
            "every_declared_class_calibrated": all(
                item["calibrated"] for item in calibration_support.values()
            ),
            "calibration_method_config_sha256": (calibration_method_config_sha256()),
            "calibration_method_config": (
                "one_vs_rest_platt_on_max_raw_probability_by_lineage_root_id"
            ),
            "model_seeds": list(model_seeds),
        }
    )
    prediction_ledger = {
        lineage: {
            "target": int(label),
            "probabilities": probability.tolist(),
        }
        for lineage, label, probability in zip(
            test_lineages, test_target, test_probabilities
        )
    }
    return result, prediction_ledger


def stratified_paired_bootstrap(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    class_count: int,
    *,
    draws: int,
    seed: int = 20260823,
) -> dict[str, Any]:
    """Resample independent lineages within class for a paired delta interval."""

    lineages = sorted(set(baseline) & set(candidate))
    if not lineages:
        raise ValueError("baseline and candidate have no common real lineages")
    target = np.asarray([baseline[root]["target"] for root in lineages], dtype=int)
    base_predictions = np.asarray(
        [np.argmax(baseline[root]["probabilities"]) for root in lineages], dtype=int
    )
    candidate_predictions = np.asarray(
        [np.argmax(candidate[root]["probabilities"]) for root in lineages], dtype=int
    )
    rng = np.random.default_rng(seed)
    labels = np.arange(class_count)
    class_positions = {
        class_id: np.flatnonzero(target == class_id)
        for class_id in labels
        if np.any(target == class_id)
    }
    differences: list[float] = []
    for _ in range(draws):
        sample = np.concatenate(
            [
                rng.choice(positions, size=len(positions), replace=True)
                for positions in class_positions.values()
            ]
        )
        base_f1 = f1_score(
            target[sample],
            base_predictions[sample],
            labels=labels,
            average="macro",
            zero_division=0,
        )
        candidate_f1 = f1_score(
            target[sample],
            candidate_predictions[sample],
            labels=labels,
            average="macro",
            zero_division=0,
        )
        differences.append(float(candidate_f1 - base_f1))
    return {
        "mean_delta_macro_f1": float(np.mean(differences)),
        "lower_95": float(np.quantile(differences, 0.025)),
        "upper_95": float(np.quantile(differences, 0.975)),
        "draws": int(draws),
        "resampling_unit": "lineage_root_id",
        "stratified_by_declared_class": True,
        "lineages": int(len(lineages)),
    }
