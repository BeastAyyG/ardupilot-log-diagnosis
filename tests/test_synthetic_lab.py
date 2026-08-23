from __future__ import annotations

import hashlib
import json

import pandas as pd
import pytest

from src.constants import FEATURE_NAMES, VALID_LABELS
from synthetic_data.ablation import run_ablation
from synthetic_data.ablation_ledger import validate_prediction_ledger
from synthetic_data.fidelity import build_fidelity_report
from synthetic_data.splits import create_split_ledger, load_and_validate_ledger


def _write_mixed_dataset(root):
    rows = []
    label_rows = []
    group_rows = []
    for label, offset in (("healthy", 0.0), ("thrust_loss", 1.0)):
        for index in range(6):
            payload = hashlib.sha256(f"real:{label}:{index}".encode()).hexdigest()
            values = [0.0] * len(FEATURE_NAMES)
            values[0] = offset + index * 0.01
            rows.append(values)
            labels = [0] * len(VALID_LABELS)
            labels[VALID_LABELS.index(label)] = 1
            label_rows.append(labels)
            group_rows.append(
                {
                    "source_log": f"real-{label}-{index}.BIN",
                    "source_group": f"real:{label}:{index}",
                    "lineage_root_id": f"real-lineage:{label}:{index}",
                    "primary_label": label,
                    "source_type": "real",
                    "verification_status": "",
                    "sha256": payload,
                    "conditioning_real_lineage_id": "",
                    "near_duplicate_cluster_id": payload,
                }
            )
    for index in range(4):
        control_run = f"control-{index}"
        fault_run = f"fault-{index}"
        for label, offset, role, run_id, paired_with in (
            ("healthy", 0.0, "sham_control", control_run, fault_run),
            ("thrust_loss", 1.0, "intervention", fault_run, control_run),
        ):
            payload = hashlib.sha256(f"sitl:{label}:{index}".encode()).hexdigest()
            values = [0.0] * len(FEATURE_NAMES)
            values[0] = offset + 0.02 + index * 0.01
            rows.append(values)
            labels = [0] * len(VALID_LABELS)
            labels[VALID_LABELS.index(label)] = 1
            label_rows.append(labels)
            group_rows.append(
                {
                    "source_log": f"sitl-{label}-{index}.BIN",
                    "source_group": f"sitl:{label}:{index}",
                    "lineage_root_id": f"sitl-pair:{index}",
                    "primary_label": label,
                    "source_type": "sitl",
                    "verification_status": "accepted",
                    "sha256": payload,
                    "artifact_sha256": payload,
                    "manifest_sha256": "a" * 64,
                    "parameter_schema_sha256": "b" * 64,
                    "run_fingerprint": hashlib.sha256(
                        f"run:{label}:{index}".encode()
                    ).hexdigest(),
                    "manifestation_predicate_sha256": "c" * 64,
                    "conditioning_real_lineage_id": "",
                    "conditioning_mode": "pure_simulation",
                    "near_duplicate_cluster_id": payload,
                    "pair_role": role,
                    "run_id": run_id,
                    "paired_with": paired_with,
                }
            )
    pd.DataFrame(rows, columns=FEATURE_NAMES).to_csv(root / "features.csv", index=False)
    pd.DataFrame(label_rows, columns=VALID_LABELS).to_csv(
        root / "labels.csv", index=False
    )
    pd.DataFrame(group_rows).to_csv(root / "groups.csv", index=False)


def test_split_fidelity_and_ablation_use_only_frozen_real_scoring(tmp_path) -> None:
    _write_mixed_dataset(tmp_path)
    ledger = create_split_ledger(
        tmp_path / "labels.csv",
        tmp_path / "groups.csv",
        tmp_path / "split.json",
        seed=9,
    )
    fidelity = build_fidelity_report(
        tmp_path / "features.csv",
        tmp_path / "labels.csv",
        tmp_path / "groups.csv",
        tmp_path / "split.json",
    )
    ablation = run_ablation(
        tmp_path / "features.csv",
        tmp_path / "labels.csv",
        tmp_path / "groups.csv",
        tmp_path / "split.json",
        output_path=tmp_path / "ablation.json",
        prediction_ledger_path=tmp_path / "predictions.json",
        synthetic_ratios=(0.5,),
        bootstrap_draws=20,
        model_seeds=(1,),
    )

    assert set(ledger["source_group_assignments"].values()) <= {
        "real_train",
        "real_calibration",
        "real_lockbox",
    }
    assert all(
        not group.startswith("sitl:") for group in ledger["source_group_assignments"]
    )
    assert fidelity["comparison_scope"].startswith("real_train")
    assert ablation["synthetic_calibration_rows"] == 0
    assert ablation["synthetic_development_test_rows"] == 0
    assert [arm["name"] for arm in ablation["arms"]] == [
        "real_only",
        "real_plus_verified_sitl_0.5x",
    ]
    prediction_path = tmp_path / "predictions.json"
    prediction_ledger = json.loads(prediction_path.read_text(encoding="utf-8"))
    validate_prediction_ledger(prediction_path, ablation)
    assert prediction_ledger["schema"] == (
        "logdiagnosis.synthetic-ablation-predictions/v1"
    )
    assert prediction_ledger["non_promoting"] is True
    assert prediction_ledger["release_authorized"] is False
    assert (
        ablation["prediction_ledger_sha256"]
        == hashlib.sha256(prediction_path.read_bytes()).hexdigest()
    )
    for arm in prediction_ledger["arms"]:
        roots = [row["lineage_root_id"] for row in arm["predictions"]]
        assert roots == sorted(set(roots))
        assert all(
            list(row["probabilities_by_class"]) == sorted(row["probabilities_by_class"])
            for row in arm["predictions"]
        )
    baseline_metrics = ablation["arms"][0]["metrics"]
    assert baseline_metrics["every_declared_class_calibrated"] is True
    assert set(baseline_metrics["calibration_per_class_real_lineages"]) == {
        "healthy",
        "thrust_loss",
    }

    second_ledger = tmp_path / "predictions-second.json"
    run_ablation(
        tmp_path / "features.csv",
        tmp_path / "labels.csv",
        tmp_path / "groups.csv",
        tmp_path / "split.json",
        output_path=tmp_path / "ablation-second.json",
        prediction_ledger_path=second_ledger,
        synthetic_ratios=(0.5,),
        bootstrap_draws=20,
        model_seeds=(1,),
    )
    assert prediction_path.read_bytes() == second_ledger.read_bytes()

    prediction_ledger["arms"][0]["predictions"][0]["target_class_id"] = 1
    prediction_path.write_text(json.dumps(prediction_ledger), encoding="utf-8")
    with pytest.raises(ValueError, match="SHA256"):
        validate_prediction_ledger(prediction_path, ablation)


def test_split_assignments_are_stable_under_row_reordering(tmp_path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    _write_mixed_dataset(first)
    features = pd.read_csv(first / "features.csv")
    labels = pd.read_csv(first / "labels.csv")
    groups = pd.read_csv(first / "groups.csv")
    order = list(reversed(range(len(features))))
    features.iloc[order].to_csv(second / "features.csv", index=False)
    labels.iloc[order].to_csv(second / "labels.csv", index=False)
    groups.iloc[order].to_csv(second / "groups.csv", index=False)

    one = create_split_ledger(
        first / "labels.csv", first / "groups.csv", first / "split.json"
    )
    two = create_split_ledger(
        second / "labels.csv", second / "groups.csv", second / "split.json"
    )
    assert one["source_group_assignments"] == two["source_group_assignments"]


def test_sparse_real_class_is_recorded_unassigned_not_indexed_as_a_partition(
    tmp_path,
) -> None:
    _write_mixed_dataset(tmp_path)
    labels = pd.read_csv(tmp_path / "labels.csv")
    groups = pd.read_csv(tmp_path / "groups.csv")
    keep = ~(
        (groups["source_type"] == "real")
        & (groups["primary_label"] == "healthy")
        & ~groups["source_group"].isin(["real:healthy:0", "real:healthy:1"])
    )
    labels.loc[keep].reset_index(drop=True).to_csv(tmp_path / "labels.csv", index=False)
    groups.loc[keep].reset_index(drop=True).to_csv(tmp_path / "groups.csv", index=False)

    ledger = create_split_ledger(
        tmp_path / "labels.csv", tmp_path / "groups.csv", tmp_path / "split.json"
    )

    assert "healthy" not in ledger["declared_model_classes"]
    assert ledger["unsupported_lockbox_classes"]["healthy"]
    assert {
        ledger["source_group_assignments"]["real:healthy:0"],
        ledger["source_group_assignments"]["real:healthy:1"],
    } == {"real_unassigned"}


def test_ledger_rejects_source_groups_that_split_one_real_lineage(tmp_path) -> None:
    _write_mixed_dataset(tmp_path)
    groups = pd.read_csv(tmp_path / "groups.csv")
    groups.loc[
        groups["source_group"].isin(["real:healthy:0", "real:healthy:1"]),
        "lineage_root_id",
    ] = "real:healthy:shared"
    groups.to_csv(tmp_path / "groups.csv", index=False)
    ledger = create_split_ledger(
        tmp_path / "labels.csv", tmp_path / "groups.csv", tmp_path / "split.json"
    )
    ledger["source_group_assignments"]["real:healthy:0"] = "real_train"
    ledger["source_group_assignments"]["real:healthy:1"] = "real_lockbox"
    (tmp_path / "split.json").write_text(json.dumps(ledger), encoding="utf-8")

    with pytest.raises(ValueError, match="assignments disagree"):
        load_and_validate_ledger(
            tmp_path / "split.json", tmp_path / "labels.csv", tmp_path / "groups.csv"
        )


def test_split_accepts_reciprocal_synthetic_pair_but_rejects_mixed_real(
    tmp_path,
) -> None:
    _write_mixed_dataset(tmp_path)
    groups = pd.read_csv(tmp_path / "groups.csv")
    labels = pd.read_csv(tmp_path / "labels.csv")
    healthy = groups.index[groups["source_group"] == "sitl:healthy:0"][0]
    fault = groups.index[groups["source_group"] == "sitl:thrust_loss:0"][0]
    groups.loc[[healthy, fault], "lineage_root_id"] = "sitl-pair:one"
    groups.loc[healthy, ["pair_role", "run_id", "paired_with"]] = [
        "sham_control",
        "healthy-run",
        "fault-run",
    ]
    groups.loc[fault, ["pair_role", "run_id", "paired_with"]] = [
        "intervention",
        "fault-run",
        "healthy-run",
    ]
    groups.to_csv(tmp_path / "groups.csv", index=False)
    create_split_ledger(
        tmp_path / "labels.csv",
        tmp_path / "groups.csv",
        tmp_path / "split.json",
    )

    real_fault = groups.index[groups["source_group"] == "real:thrust_loss:0"][0]
    real_healthy = groups.index[groups["source_group"] == "real:healthy:0"][0]
    groups.loc[[real_fault, real_healthy], "lineage_root_id"] = "real:mixed"
    groups.to_csv(tmp_path / "groups.csv", index=False)
    labels.to_csv(tmp_path / "labels.csv", index=False)
    with pytest.raises(ValueError, match="invalid mixed"):
        create_split_ledger(
            tmp_path / "labels.csv",
            tmp_path / "groups.csv",
            tmp_path / "bad-split.json",
        )
