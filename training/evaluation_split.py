"""Leakage-resistant train/test splitting for windowed flight-log data."""

from __future__ import annotations

import numpy as np
from sklearn.model_selection import GroupShuffleSplit, StratifiedGroupKFold


def grouped_train_test_split(
    labels: np.ndarray,
    groups: np.ndarray,
    test_size: float = 0.2,
    random_state: int = 42,
) -> tuple[np.ndarray, np.ndarray]:
    """Split rows while keeping every source log in exactly one partition."""
    labels = np.asarray(labels)
    groups = np.asarray(groups)
    if len(labels) != len(groups):
        raise ValueError("Labels and source-log groups must have the same row count.")
    if len(labels) < 2:
        raise ValueError("At least two rows are required for a grouped split.")

    classes = set(labels.tolist())
    # Prefer stratified group folds so every failure class is represented in
    # the holdout when the corpus contains enough independent source logs.
    requested_splits = max(2, round(1.0 / test_size))
    _, class_counts = np.unique(labels, return_counts=True)
    # Newer scikit-learn versions reject a fold count larger than the rarest
    # class. Sparse smoke-test corpora commonly have only two rows per class;
    # cap the fold count and let the grouped fallback handle singleton classes.
    n_splits = min(requested_splits, int(class_counts.min()), len(np.unique(groups)))
    candidates = []
    if n_splits >= 2:
        stratified = StratifiedGroupKFold(
            n_splits=n_splits, shuffle=True, random_state=random_state
        )
        candidates = list(stratified.split(np.zeros(len(labels)), labels, groups))
    candidates.sort(
        key=lambda pair: (
            len(set(labels[pair[1]].tolist()) ^ classes),
            abs(len(pair[1]) / len(labels) - test_size),
        )
    )
    for train_idx, test_idx in candidates:
        # Every class must remain learnable in training. A class may be absent
        # from the holdout when the labeled corpus is still small; its holdout
        # support is then reported as zero rather than leaking another window
        # from that source log into training.
        if set(labels[train_idx].tolist()) == classes and len(test_idx) > 0:
            if set(groups[train_idx].tolist()).isdisjoint(set(groups[test_idx].tolist())):
                return train_idx, test_idx

    # Fall back to repeated grouped random splits only for unusually sparse
    # corpora where stratification cannot place every class in the holdout.
    splitter = GroupShuffleSplit(
        n_splits=100, test_size=test_size, random_state=random_state
    )
    for train_idx, test_idx in splitter.split(np.zeros(len(labels)), labels, groups):
        if set(labels[train_idx].tolist()) == classes and len(test_idx) > 0:
            if set(groups[train_idx].tolist()).isdisjoint(set(groups[test_idx].tolist())):
                return train_idx, test_idx

    raise ValueError(
        "Could not create a grouped split containing every class in both partitions. "
        "Add more independently labeled source logs before training."
    )


def real_holdout_train_test_split(
    labels: np.ndarray,
    groups: np.ndarray,
    source_types: np.ndarray,
    test_size: float = 0.2,
    random_state: int = 42,
) -> tuple[np.ndarray, np.ndarray]:
    """Keep every synthetic/SITL/HIL row in training and test only on real logs.

    Classes represented only by simulation remain learnable experiments, but
    receive zero real holdout support.  Their synthetic performance therefore
    cannot inflate the release Macro F1 or calibration score.
    """

    labels = np.asarray(labels)
    groups = np.asarray(groups)
    source_types = np.asarray(source_types)
    if len(labels) != len(groups) or len(labels) != len(source_types):
        raise ValueError("Labels, groups, and source types must have the same row count.")

    allowed_types = {"real", "sitl", "hil", "feature_synthetic", "simulation"}
    unknown_types = sorted(set(source_types.tolist()) - allowed_types)
    if unknown_types:
        raise ValueError(
            "Unknown provenance cannot enter a real-only split: "
            + ", ".join(str(value) for value in unknown_types)
        )
    synthetic_types = allowed_types - {"real"}
    synthetic_mask = np.isin(source_types, tuple(synthetic_types))
    real_indices = np.flatnonzero(source_types == "real")
    synthetic_indices = np.flatnonzero(synthetic_mask)
    if len(real_indices) < 2:
        raise ValueError("At least two real rows are required for a real-only holdout.")

    real_train, real_test = grouped_train_test_split(
        labels[real_indices],
        groups[real_indices],
        test_size=test_size,
        random_state=random_state,
    )
    train_indices = np.concatenate((real_indices[real_train], synthetic_indices))
    test_indices = real_indices[real_test]
    if np.isin(source_types[test_indices], tuple(synthetic_types)).any():
        raise AssertionError("Synthetic data entered the real-only holdout.")
    if not np.all(source_types[test_indices] == "real"):
        raise AssertionError("Non-real provenance entered the real-only holdout.")
    return np.sort(train_indices), np.sort(test_indices)
