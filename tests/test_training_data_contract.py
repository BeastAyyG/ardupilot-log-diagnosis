import numpy as np
import pandas as pd
import json
import hashlib

from src.constants import VALID_LABELS
from training.data_contract import (
    ambiguous_group_labels,
    canonical_source_group,
    effective_source_types,
    effective_group_values,
    primary_label_for_row,
    real_source_mask,
    synthetic_source_mask,
    unknown_source_mask,
)
from training.train_model import _validate_group_label_contract
from training.validate_artifact import _group_label_errors
from training.create_unseen_holdout import _merge_nonempty
from training.measure_ece import aggregate_group_probabilities


def test_source_url_groups_same_incident_and_ignore_download_query():
    first = {
        "source_url": "https://discuss.ardupilot.org/t/case-123/99?download=1",
    }
    second = {
        "source_url": "https://discuss.ardupilot.org/t/case-123/99?dl=1&utm_source=x",
    }
    assert canonical_source_group(first, "a.bin") == canonical_source_group(
        second, "b.bin"
    )


def test_explicit_primary_label_overrides_runtime_column_order():
    labels = pd.Series(
        [0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0],
        index=VALID_LABELS,
    )
    # VALID_LABELS puts compass_interference before ekf_failure, but source
    # provenance explicitly says the root cause is EKF failure.
    assert primary_label_for_row(
        labels, preferred="ekf_failure", allowed=VALID_LABELS
    ) == "ekf_failure"


def test_effective_group_values_prefer_incident_groups():
    groups = pd.DataFrame(
        {
            "source_log": ["a.bin", "b.bin"],
            "source_group": ["url:case", "url:case"],
        }
    )
    assert np.array_equal(effective_group_values(groups), np.array(["url:case"] * 2))


def test_source_type_contract_detects_explicit_and_legacy_synthetic_rows():
    groups = pd.DataFrame(
        {
            "source_log": ["forum.bin", "sitl.BIN", "old.csv"],
            "source_group": ["url:case", "sitl:run-1", "synthetic:thrust:1"],
            "source_type": ["ArduPilot Discuss", "SITL_SIMULATION", ""],
        }
    )

    assert effective_source_types(groups).tolist() == [
        "real",
        "sitl",
        "feature_synthetic",
    ]
    assert synthetic_source_mask(groups).tolist() == [False, True, True]


def test_source_type_contract_is_fail_closed_for_missing_unknown_and_basic():
    groups = pd.DataFrame(
        {
            "source_log": ["missing.bin", "novel.bin", "basic.bin", "hil.bin", "real.bin"],
            "source_group": ["", "", "", "", ""],
            "source_type": [np.nan, "new_vendor_export", "BASiC_dataset", "HIL_SIMULATION", "real"],
        }
    )

    assert effective_source_types(groups).tolist() == [
        "unknown",
        "unknown",
        "simulation",
        "hil",
        "real",
    ]
    assert real_source_mask(groups).tolist() == [False, False, False, False, True]
    assert unknown_source_mask(groups).tolist() == [True, True, False, False, False]


def test_holdout_metadata_merge_does_not_erase_manifest_url():
    merged = _merge_nonempty(
        {"source_url": "https://discuss.ardupilot.org/t/case/1"},
        {"source_url": "", "labels": ["vibration_high"]},
    )
    assert merged["source_url"].endswith("/case/1")


def test_ece_aggregation_scores_one_probability_vector_per_incident():
    y_true = np.array([0, 0, 1])
    probs = np.array([[0.2, 0.8], [0.9, 0.1], [0.1, 0.9]])
    groups = np.array(["incident-a", "incident-a", "incident-b"])
    y, p = aggregate_group_probabilities(y_true, probs, groups)
    assert y.tolist() == [0, 1]
    assert p.tolist() == [[0.9, 0.8], [0.1, 0.9]]


def test_conflicting_labels_in_one_source_group_are_not_scorable():
    labels = pd.DataFrame(
        [
            [0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0],
        ],
        columns=VALID_LABELS,
    )
    groups = pd.DataFrame(
        {
            "source_log": ["a.bin", "b.bin"],
            "source_group": ["url:case", "url:case"],
        }
    )
    found = ambiguous_group_labels(labels, groups, VALID_LABELS)
    assert found == {"url:case": ("compass_interference", "ekf_failure")}
    assert _group_label_errors(labels, groups)
    try:
        _validate_group_label_contract(labels, groups)
    except ValueError as exc:
        assert "Ambiguous source groups" in str(exc)
    else:  # pragma: no cover - assertion makes the failure message explicit
        raise AssertionError("conflicting source labels must fail closed")


def test_ambiguous_group_check_uses_row_position_not_dataframe_index():
    labels = pd.DataFrame(
        [
            [0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0],
        ],
        columns=VALID_LABELS,
        index=[10, 20],
    )
    groups = pd.DataFrame(
        {"source_log": ["a.bin", "b.bin"], "source_group": ["case", "case"]},
        index=[10, 20],
    )
    assert ambiguous_group_labels(labels, groups, VALID_LABELS) == {
        "case": ("compass_interference", "ekf_failure")
    }


def test_build_dataset_excludes_conflicting_source_url_group(tmp_path, monkeypatch):
    import training.build_dataset as build_dataset

    class DummyParser:
        def __init__(self, path):
            self.path = path

        def parse(self):
            return {"messages": {"GPS": [{"TimeUS": 0}]}, "metadata": {}}

    class DummyPipeline:
        def extract(self, parsed):
            return {name: 0.0 for name in VALID_LABELS}

    monkeypatch.setattr(build_dataset, "LogParser", DummyParser)
    monkeypatch.setattr(build_dataset, "FeaturePipeline", DummyPipeline)
    monkeypatch.setattr(
        build_dataset,
        "slice_log_into_windows",
        lambda parsed, window_sec, overlap: [parsed],
    )

    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir()
    for name in ("a.bin", "b.bin"):
        (dataset_dir / name).write_bytes(name.encode())
    gt = {
        "logs": [
            {
                "filename": "a.bin",
                "labels": ["compass_interference"],
                "source_url": "https://discuss.ardupilot.org/t/case/1",
            },
            {
                "filename": "b.bin",
                "labels": ["ekf_failure"],
                "source_url": "https://discuss.ardupilot.org/t/case/1",
            },
        ]
    }
    gt_path = tmp_path / "ground_truth.json"
    gt_path.write_text(json.dumps(gt), encoding="utf-8")
    result = build_dataset.build(
        ground_truth_path=str(gt_path),
        dataset_dir=str(dataset_dir),
        output_features=str(tmp_path / "features.csv"),
        output_labels=str(tmp_path / "labels.csv"),
        output_groups=str(tmp_path / "groups.csv"),
        report_path=str(tmp_path / "report.json"),
    )
    assert result["skipped_ambiguous_group"] == 2
    assert result["processed"] == 0
    assert result["ambiguous_source_groups"]


def test_build_dataset_uses_only_post_onset_synthetic_windows(tmp_path, monkeypatch):
    import training.build_dataset as build_dataset

    parsed = {"messages": {"GPS": [{"TimeUS": 0}]}, "metadata": {}}

    class DummyParser:
        def __init__(self, path):
            self.path = path

        def parse(self):
            return parsed

    class DummyPipeline:
        def extract(self, log_slice):
            return {}

    def sliced(_parsed, window_sec, overlap):
        return [
            {"messages": {}, "metadata": {"window_start": 0.0, "window_end": 5.0}},
            {"messages": {}, "metadata": {"window_start": 9.0, "window_end": 14.0}},
            {"messages": {}, "metadata": {"window_start": 12.0, "window_end": 17.0}},
        ]

    monkeypatch.setattr(build_dataset, "LogParser", DummyParser)
    monkeypatch.setattr(build_dataset, "FeaturePipeline", DummyPipeline)
    monkeypatch.setattr(build_dataset, "slice_log_into_windows", sliced)

    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir()
    payload = b"verified-sitl"
    (dataset_dir / "fault.BIN").write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    ground_truth = {
        "logs": [
            {
                "filename": "fault.BIN",
                "labels": ["thrust_loss"],
                "source_group": "sitl:test",
                "lineage_root_id": "sitl-lineage:test",
                "source_type": "sitl",
                "trainable": True,
                    "verification_status": "accepted",
                    "artifact_sha256": digest,
                    "manifest_sha256": "a" * 64,
                    "parameter_schema_sha256": "b" * 64,
                    "run_fingerprint": "c" * 64,
                    "manifestation_predicate_sha256": "d" * 64,
                    "fault_onset_sec": 10.0,
            }
        ]
    }
    ground_truth_path = tmp_path / "ground_truth.json"
    ground_truth_path.write_text(json.dumps(ground_truth), encoding="utf-8")
    result = build_dataset.build(
        ground_truth_path=str(ground_truth_path),
        dataset_dir=str(dataset_dir),
        output_features=str(tmp_path / "features.csv"),
        output_labels=str(tmp_path / "labels.csv"),
        output_groups=str(tmp_path / "groups.csv"),
        report_path=str(tmp_path / "report.json"),
    )
    groups = pd.read_csv(tmp_path / "groups.csv")

    assert result["processed"] == 1
    assert result["excluded_pre_fault_windows"] == 1
    assert result["excluded_transition_windows"] == 1
    assert result["excluded_mixed_full_logs"] == 1
    assert groups["window_phase"].tolist() == ["post_fault"]
    assert groups["window_start_sec"].tolist() == [12.0]
