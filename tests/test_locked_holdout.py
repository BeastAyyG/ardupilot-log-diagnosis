import json

import numpy as np
import pytest

from training.train_model import _locked_holdout_indices


def test_locked_holdout_preserves_ids_and_class_coverage(tmp_path):
    groups = np.array(["a1", "a2", "b1", "b2", "new"])
    labels = np.array(["a", "a", "b", "b", "a"])
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"test_flight_ids": ["a2", "b2"]}),
        encoding="utf-8",
    )

    train_idx, test_idx = _locked_holdout_indices(
        groups,
        labels,
        str(manifest),
    )

    assert set(groups[test_idx]) == {"a2", "b2"}
    assert set(groups[train_idx]) == {"a1", "b1", "new"}


def test_locked_holdout_rejects_missing_flight(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"test_flight_ids": ["missing"]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="missing from the current dataset"):
        _locked_holdout_indices(
            np.array(["a"]),
            np.array(["class_a"]),
            str(manifest),
        )
