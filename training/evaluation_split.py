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
