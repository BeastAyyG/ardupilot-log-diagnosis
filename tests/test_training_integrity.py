import numpy as np
import pandas as pd
import pytest

from src.constants import FEATURE_NAMES, VALID_LABELS
from training.evaluation_split import grouped_train_test_split
from training.train_model import _validate_training_inputs
from training.window_slicer import slice_log_into_windows


def test_window_slicer_uses_parser_timeus_values():
    parsed = {
        "metadata": {},
        "messages": {
            "IMU": [{"TimeUS": 0}, {"TimeUS": 3_000_000}, {"TimeUS": 6_000_000}],
            "VIBE": [{"TimeUS": 1_000_000}, {"TimeUS": 4_000_000}, {"TimeUS": 7_000_000}],
            "GPS": [{"TimeUS": 2_000_000}, {"TimeUS": 5_000_000}, {"TimeUS": 8_000_000}],
        },
    }

    windows = slice_log_into_windows(parsed, window_sec=4.0, overlap=0.0)

    assert len(windows) == 2
    assert all(window["metadata"]["duration_sec"] == 4.0 for window in windows)
    assert all(window["messages"]["IMU"] for window in windows)


def test_grouped_split_keeps_source_logs_disjoint_and_classes_present():
    labels = np.array(["vibration", "vibration", "ekf", "ekf", "power", "power"])
    groups = np.array(["a", "b", "a", "b", "a", "b"])

    train_idx, test_idx = grouped_train_test_split(labels, groups, test_size=0.34)

    assert set(groups[train_idx]).isdisjoint(set(groups[test_idx]))
    assert set(labels[train_idx]) == set(labels)
    assert set(labels[test_idx]).issubset(set(labels))


def test_training_rejects_a_stale_feature_schema_before_fitting():
    features = pd.DataFrame([[0.0] * len(FEATURE_NAMES)], columns=FEATURE_NAMES)
    labels = pd.DataFrame([[0] * len(VALID_LABELS)], columns=VALID_LABELS)
    groups = pd.DataFrame({"source_log": ["log.bin"]})

    _validate_training_inputs(features, labels, groups)

    with pytest.raises(ValueError, match="Feature schema mismatch"):
        _validate_training_inputs(features.iloc[:, :-1], labels, groups)
