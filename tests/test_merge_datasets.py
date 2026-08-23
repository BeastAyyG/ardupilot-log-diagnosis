from __future__ import annotations

import hashlib
import json

import pandas as pd
import pytest

from src.constants import FEATURE_NAMES, VALID_LABELS
from training.merge_datasets import (
    BUILD_SCHEMA,
    CONTRACT_FIELDS,
    PROVENANCE_COLUMNS,
    merge_datasets,
)
from training.model_training_contract import load_dataset_contract


def _hash(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _dataset(root, *, source_group: str, source_type: str, sha256: str) -> None:
    root.mkdir()
    pd.DataFrame([[0.0] * len(FEATURE_NAMES)], columns=FEATURE_NAMES).to_csv(
        root / "features.csv", index=False
    )
    label = [0] * len(VALID_LABELS)
    label[VALID_LABELS.index("healthy")] = 1
    pd.DataFrame([label], columns=VALID_LABELS).to_csv(root / "labels.csv", index=False)
    row = {column: "" for column in PROVENANCE_COLUMNS}
    row.update(
        {
            "source_log": f"{source_group}.BIN",
            "source_group": source_group,
            "lineage_root_id": source_group,
            "source_type": source_type,
            "sha256": sha256,
            "artifact_sha256": sha256,
            "verification_status": (
                "accepted" if source_type.lower() not in {"real", "hardware"} else ""
            ),
            "window_phase": "window",
        }
    )
    if source_type.lower() not in {"real", "hardware"}:
        row.update(
            {
                "manifest_sha256": "4" * 64,
                "parameter_schema_sha256": "5" * 64,
                "run_fingerprint": "6" * 64,
                "manifestation_predicate_sha256": "7" * 64,
            }
        )
    pd.DataFrame([row], columns=PROVENANCE_COLUMNS).to_csv(
        root / "groups.csv", index=False
    )
    contract = {
        "feature_schema_sha256": "1" * 64,
        "label_schema_sha256": "2" * 64,
        "extractor_source_sha256": "3" * 64,
        "window_sec": 30.0,
        "overlap": 0.5,
        "transition_guard_sec": 2.0,
        "window_policy": "test",
        "include_full_log": "test",
    }
    assert set(contract) == set(CONTRACT_FIELDS)
    report = {
        "schema": BUILD_SCHEMA,
        **contract,
        "features_sha256": _hash(root / "features.csv"),
        "labels_sha256": _hash(root / "labels.csv"),
        "groups_sha256": _hash(root / "groups.csv"),
    }
    (root / "dataset_build_report.json").write_text(
        json.dumps(report), encoding="utf-8"
    )


def test_merge_preserves_source_types_and_schema(tmp_path) -> None:
    real = tmp_path / "real"
    sitl = tmp_path / "sitl"
    output = tmp_path / "mixed"
    _dataset(real, source_group="real:1", source_type="real", sha256="a" * 64)
    _dataset(
        sitl, source_group="sitl:1", source_type="SITL_SIMULATION", sha256="b" * 64
    )

    report = merge_datasets([real, sitl], output)
    groups = pd.read_csv(output / "groups.csv")

    assert report["rows"] == 2
    assert groups["source_type"].tolist() == ["real", "sitl"]
    assert (output / "merge_report.json").exists()
    window, _ = load_dataset_contract(
        str(output / "merge_report.json"),
        features_csv=str(output / "features.csv"),
        labels_csv=str(output / "labels.csv"),
        groups_csv=str(output / "groups.csv"),
    )
    assert window["window_sec"] == 30.0
    assert window["source"] == "merged_dataset_report"


def test_merge_rejects_cross_input_payload_duplicates(tmp_path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    _dataset(first, source_group="one", source_type="real", sha256="a" * 64)
    _dataset(second, source_group="two", source_type="sitl", sha256="a" * 64)

    with pytest.raises(ValueError, match="duplicates"):
        merge_datasets([first, second], tmp_path / "output")


def test_merge_rejects_incompatible_window_contracts(tmp_path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    _dataset(first, source_group="one", source_type="real", sha256="a" * 64)
    _dataset(second, source_group="two", source_type="sitl", sha256="b" * 64)
    report_path = second / "dataset_build_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["window_sec"] = 5.0
    report_path.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(ValueError, match="incompatible extraction contract"):
        merge_datasets([first, second], tmp_path / "output")
