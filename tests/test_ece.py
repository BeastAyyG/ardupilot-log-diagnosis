import numpy as np

from training.measure_ece import compute_ece


def test_ece_counts_probability_one_in_last_bin():
    y_true = np.array([0, 1])
    probabilities = np.array([[1.0, 0.0], [0.0, 1.0]])

    assert compute_ece(y_true, probabilities) == 0.0


def test_ece_uses_top_label_confidence():
    y_true = np.array([0, 1])
    probabilities = np.array([[0.9, 0.1], [0.9, 0.1]])

    assert np.isclose(compute_ece(y_true, probabilities), 0.4)
