import numpy as np
import pandas as pd
import pytest

from src.constants import FEATURE_NAMES, VALID_LABELS
from training.evaluation_split import (
    grouped_train_test_split,
    real_holdout_train_test_split,
)
from training.model_training_contract import validate_production_provenance
from training.train_helpers import validate_descendants as _validate_descendants
from training.train_model import _validate_training_inputs, train
from training.window_slicer import slice_log_into_windows


def test_window_slicer_uses_parser_timeus_values():
    parsed = {
        "metadata": {},
        "messages": {
            "IMU": [{"TimeUS": 0}, {"TimeUS": 3_000_000}, {"TimeUS": 6_000_000}],
            "VIBE": [
                {"TimeUS": 1_000_000},
                {"TimeUS": 4_000_000},
                {"TimeUS": 7_000_000},
            ],
            "GPS": [
                {"TimeUS": 2_000_000},
                {"TimeUS": 5_000_000},
                {"TimeUS": 8_000_000},
            ],
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


def test_real_holdout_keeps_all_synthetic_rows_in_training():
    labels = np.array(["vibration", "vibration", "power", "power", "thrust", "thrust"])
    groups = np.array(["real-a", "real-b", "real-c", "real-d", "sitl-a", "sitl-b"])
    source_types = np.array(["real", "real", "real", "real", "sitl", "sitl"])

    train_idx, test_idx = real_holdout_train_test_split(
        labels, groups, source_types, test_size=0.5
    )

    assert {4, 5}.issubset(set(train_idx.tolist()))
    assert set(source_types[test_idx]) == {"real"}
    assert set(groups[train_idx]).isdisjoint(set(groups[test_idx]))


def test_real_holdout_rejects_unknown_provenance():
    labels = np.array(["healthy", "healthy", "power"])
    groups = np.array(["real-a", "real-b", "unknown-a"])
    source_types = np.array(["real", "real", "unknown"])

    with pytest.raises(ValueError, match="Unknown provenance"):
        real_holdout_train_test_split(labels, groups, source_types, test_size=0.5)


def test_training_rejects_a_stale_feature_schema_before_fitting():
    features = pd.DataFrame([[0.0] * len(FEATURE_NAMES)], columns=FEATURE_NAMES)
    labels = pd.DataFrame([[0] * len(VALID_LABELS)], columns=VALID_LABELS)
    groups = pd.DataFrame({"source_log": ["log.bin"]})

    _validate_training_inputs(features, labels, groups)

    with pytest.raises(ValueError, match="Feature schema mismatch"):
        _validate_training_inputs(features.iloc[:, :-1], labels, groups)


def test_training_requires_a_frozen_split_ledger_before_reading_inputs():
    with pytest.raises(ValueError, match="frozen --split-ledger"):
        train(split_ledger_path=None)


def test_production_provenance_rejects_unverified_physical_flights():
    groups = pd.DataFrame(
        {
            "source_type": ["real"],
            "physical_flight_verified": [False],
            "verification_status": [""],
            "manifest_sha256": [""],
            "parameter_schema_sha256": [""],
            "artifact_sha256": [""],
            "run_fingerprint": [""],
            "manifestation_predicate_sha256": [""],
            "sha256": ["a" * 64],
        }
    )

    with pytest.raises(ValueError, match="verified physical flight"):
        validate_production_provenance(groups, {})


def test_production_provenance_rejects_unverified_synthetic_rows():
    groups = pd.DataFrame(
        {
            "source_type": ["sitl"],
            "physical_flight_verified": [False],
            "verification_status": ["pending"],
            "manifest_sha256": ["a" * 64],
            "parameter_schema_sha256": ["b" * 64],
            "artifact_sha256": ["c" * 64],
            "run_fingerprint": ["d" * 64],
            "manifestation_predicate_sha256": ["e" * 64],
            "sha256": ["c" * 64],
        }
    )

    with pytest.raises(ValueError, match="accepted verification status"):
        validate_production_provenance(groups, {})


def test_training_rejects_synthetic_descendants_of_protected_lineages():
    groups = pd.DataFrame(
        {
            "conditioning_real_lineage_id": ["real-calibration", ""],
            "conditioning_mode": ["real_conditioned", ""],
        }
    )
    source_types = np.array(["sitl", "real"])

    with pytest.raises(ValueError, match="protected real lineages"):
        _validate_descendants(groups, source_types, {"real-calibration"})
