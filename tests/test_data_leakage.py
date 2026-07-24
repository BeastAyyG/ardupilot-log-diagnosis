import numpy as np
import pytest

from training.dataset_integrity import (
    assert_group_isolation,
    stratified_group_holdout_indices,
)


def test_group_split_keeps_complete_flights_together():
    flights = [f"flight_{index}.bin" for index in range(10)]
    groups = np.array(
        [flight for flight in flights for _window_index in range(5)]
    )

    train_idx = np.flatnonzero(np.isin(groups, flights[:8]))
    test_idx = np.flatnonzero(np.isin(groups, flights[8:]))

    assert_group_isolation(groups, train_idx, test_idx)
    assert len(set(groups[train_idx])) == 8
    assert len(set(groups[test_idx])) == 2


def test_group_isolation_rejects_cross_split_flight():
    groups = np.array(["flight_a", "flight_a", "flight_b"])

    with pytest.raises(ValueError, match="Flight-group leakage"):
        assert_group_isolation(groups, [0, 2], [1])


def test_stratified_group_holdout_covers_each_class():
    labels = np.array(
        [label for label in ("healthy", "failure") for _flight in range(5) for _window in range(2)]
    )
    groups = np.array(
        [
            f"{label}_{flight}"
            for label in ("healthy", "failure")
            for flight in range(5)
            for _window in range(2)
        ]
    )

    train_idx, test_idx = stratified_group_holdout_indices(labels, groups)

    assert_group_isolation(groups, train_idx, test_idx)
    assert set(labels[test_idx]) == {"healthy", "failure"}
    assert len(set(groups[test_idx])) == 2
