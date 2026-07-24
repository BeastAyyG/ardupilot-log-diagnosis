"""Integrity checks shared by dataset building, training, and tests."""

from __future__ import annotations

import random
from collections.abc import Sequence


def assert_group_isolation(
    groups: Sequence,
    train_indices: Sequence[int],
    test_indices: Sequence[int],
) -> None:
    """Raise when any source flight appears in both train and test."""
    train_groups = {groups[index] for index in train_indices}
    test_groups = {groups[index] for index in test_indices}
    overlap = train_groups.intersection(test_groups)
    if overlap:
        preview = ", ".join(sorted(str(item) for item in overlap)[:5])
        raise ValueError(f"Flight-group leakage detected: {preview}")


def stratified_group_holdout_indices(
    labels: Sequence,
    groups: Sequence,
    test_fraction: float = 0.2,
    random_state: int = 42,
) -> tuple[list[int], list[int]]:
    """Select a deterministic, class-covered holdout of complete flights."""
    if len(labels) != len(groups):
        raise ValueError("labels and groups must have equal length")
    if not 0.0 < test_fraction < 1.0:
        raise ValueError("test_fraction must be between zero and one")

    group_labels = {}
    for label, group in zip(labels, groups):
        previous = group_labels.setdefault(group, label)
        if previous != label:
            raise ValueError(f"Conflicting labels for flight group {group}")

    groups_by_label = {}
    for group, label in group_labels.items():
        groups_by_label.setdefault(label, []).append(group)

    rng = random.Random(random_state)
    test_groups = set()
    for label in sorted(groups_by_label, key=str):
        class_groups = sorted(groups_by_label[label], key=str)
        rng.shuffle(class_groups)
        test_count = max(1, round(len(class_groups) * test_fraction))
        test_count = min(test_count, len(class_groups) - 1)
        test_groups.update(class_groups[:test_count])

    test_indices = [
        index for index, group in enumerate(groups) if group in test_groups
    ]
    train_indices = [
        index for index, group in enumerate(groups) if group not in test_groups
    ]
    assert_group_isolation(groups, train_indices, test_indices)
    return train_indices, test_indices
