"""Goal 04: preregistered fidelity design manifest is the denominator."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from synthetic_data.fidelity import (
    DESIGN_SCHEMA,
    build_fidelity_report,
    evaluate_design_manifest,
)
from synthetic_data.schema import sha256_file
from synthetic_data.splits import create_split_ledger

STRATIFIERS = (
    "primary_label",
    "flight_phase",
    "vehicle_frame",
    "firmware_commit",
    "simulation_family",
)


def _write_dataset(
    root: Path,
    *,
    supported_stratum: bool = True,
    synthetic_pairs: int = 3,
    real_per_label: int = 6,
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    import pandas as pd

    from src.constants import FEATURE_NAMES, VALID_LABELS

    rows, label_rows, group_rows = [], [], []

    def add_row(source_type, label, lineage, group, offset, **strata):
        payload = hashlib.sha256(group.encode()).hexdigest()
        values = [0.0] * len(FEATURE_NAMES)
        values[0] = offset
        rows.append(values)
        labels = [0] * len(VALID_LABELS)
        labels[VALID_LABELS.index(label)] = 1
        label_rows.append(labels)
        record = {
            "source_log": f"{group}.BIN",
            "source_group": group,
            "lineage_root_id": lineage,
            "primary_label": label,
            "source_type": source_type,
            "sha256": payload,
            "conditioning_real_lineage_id": "",
            "near_duplicate_cluster_id": payload,
            **{name: strata.get(name, "") for name in STRATIFIERS[1:]},
        }
        if source_type != "real":
            record["verification_status"] = "accepted"
            record["conditioning_mode"] = "pure_simulation"
        else:
            record["verification_status"] = ""
        for extra in ("pair_role", "run_id", "paired_with"):
            if extra in strata:
                record[extra] = strata[extra]
        group_rows.append(record)

    def add_synth_pair(index: int, *, fault_family: str) -> None:
        lineage = f"synth-pair:{index}"
        add_row(
            "sitl",
            "healthy",
            lineage,
            f"sitl:healthy:{index}",
            -0.4 - index * 0.01,
            flight_phase="hover",
            vehicle_frame="quad",
            firmware_commit="Copter-4.6.2",
            simulation_family="healthy",
            pair_role="sham_control",
            run_id=f"control-{index}",
            paired_with=f"fault-{index}",
        )
        add_row(
            "sitl",
            "thrust_loss",
            lineage,
            f"sitl:fault:{index}",
            0.4 + index * 0.01,
            flight_phase="hover",
            vehicle_frame="quad",
            firmware_commit="Copter-4.6.2",
            simulation_family=fault_family,
            pair_role="intervention",
            run_id=f"fault-{index}",
            paired_with=f"control-{index}",
        )

    for pair in range(synthetic_pairs):
        add_synth_pair(
            pair, fault_family="thrust_loss" if supported_stratum else "other_family"
        )
    for index in range(real_per_label):
        add_row(
            "real",
            "healthy",
            f"real-healthy-lin:{index}",
            f"real:healthy:{index}",
            -0.1 - index * 0.01,
            flight_phase="hover",
            vehicle_frame="quad",
            firmware_commit="Copter-4.6.2",
            simulation_family="physical",
        )
    for index in range(real_per_label):
        add_row(
            "real",
            "thrust_loss",
            f"real-lin:{index}",
            f"real:{index}",
            0.1 + index * 0.01,
            flight_phase="hover",
            vehicle_frame="quad",
            firmware_commit="Copter-4.6.2",
            simulation_family="physical",
        )
    pd.DataFrame(rows, columns=FEATURE_NAMES).to_csv(root / "features.csv", index=False)
    pd.DataFrame(label_rows, columns=VALID_LABELS).to_csv(
        root / "labels.csv", index=False
    )
    pd.DataFrame(group_rows).to_csv(root / "groups.csv", index=False)


def _manifest(root: Path, entries: list[dict], minimum: int = 3) -> Path:
    manifest = {
        "schema": DESIGN_SCHEMA,
        "minimum_units_per_domain_per_stratum": minimum,
        "required_strata": entries,
    }
    path = root / "design_manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


_SUPPORTED = {
    "primary_label": "thrust_loss",
    "flight_phase": "hover",
    "vehicle_frame": "quad",
    "firmware_commit": "Copter-4.6.2",
    "simulation_family": "thrust_loss",
}


def test_supported_required_stratum_is_evaluated_and_hash_bound(tmp_path) -> None:
    _write_dataset(tmp_path, supported_stratum=True)
    create_split_ledger(
        tmp_path / "labels.csv",
        tmp_path / "groups.csv",
        tmp_path / "split.json",
        declared_classes=["healthy", "thrust_loss"],
    )
    manifest_path = _manifest(tmp_path, [dict(_SUPPORTED)])

    report = build_fidelity_report(
        tmp_path / "features.csv",
        tmp_path / "labels.csv",
        tmp_path / "groups.csv",
        tmp_path / "split.json",
        design_manifest_path=manifest_path,
    )

    assert report["status"] == "measured_conditionally_not_promoted"
    assert report["design_manifest_sha256"] == sha256_file(manifest_path)
    assert report["design_required_strata"] == 1
    assert report["evaluated_required_strata"] == 1
    assert report["missing_required_strata"] == 0
    assert report["minimum_units_per_domain_per_stratum"] == 3
    assert report["nonlinear_c2st_complete"] is True
    assert report["mmd_complete"] is True
    assert report["source_classifier_permutation_draws"] == 1000
    assert 0 < report["source_classifier_permutation_p_value"] <= 1
    assert report["stratifiers"] == list(STRATIFIERS)
    assert report["global_unit"] == "lineage_root_id"
    assert report["synthetic_units"] == 3


def test_missing_or_under_supported_strata_block_and_are_listed(tmp_path) -> None:
    _write_dataset(tmp_path, supported_stratum=True)
    create_split_ledger(
        tmp_path / "labels.csv",
        tmp_path / "groups.csv",
        tmp_path / "split.json",
        declared_classes=["healthy", "thrust_loss"],
    )
    absent = dict(_SUPPORTED, simulation_family="never_generated")
    manifest_path = _manifest(tmp_path, [dict(_SUPPORTED), absent])

    report = build_fidelity_report(
        tmp_path / "features.csv",
        tmp_path / "labels.csv",
        tmp_path / "groups.csv",
        tmp_path / "split.json",
        design_manifest_path=manifest_path,
    )

    assert report["status"] == "blocked_incomplete_conditional_fidelity"
    assert report["design_required_strata"] == 2
    assert report["evaluated_required_strata"] == 1
    assert report["missing_required_strata"] == 1
    assert report["design_evaluation"]["missing_strata_detail"] == [absent]


def test_low_support_blocks_even_when_the_stratum_exists(tmp_path) -> None:
    _write_dataset(tmp_path, supported_stratum=True)
    create_split_ledger(
        tmp_path / "labels.csv",
        tmp_path / "groups.csv",
        tmp_path / "split.json",
        declared_classes=["healthy", "thrust_loss"],
    )
    manifest_path = _manifest(tmp_path, [dict(_SUPPORTED)], minimum=50)

    report = build_fidelity_report(
        tmp_path / "features.csv",
        tmp_path / "labels.csv",
        tmp_path / "groups.csv",
        tmp_path / "split.json",
        design_manifest_path=manifest_path,
    )
    assert report["missing_required_strata"] == 1


def test_design_manifest_validation_fails_closed(tmp_path) -> None:
    _write_dataset(tmp_path)
    good = {
        "schema": DESIGN_SCHEMA,
        "minimum_units_per_domain_per_stratum": 3,
        "required_strata": [dict(_SUPPORTED)],
    }
    path = tmp_path / "m.json"

    bad_schema = dict(good, schema="other/v9")
    bad_empty = dict(good, required_strata=[])
    bad_key = {
        **good,
        "required_strata": [
            {k: v for k, v in _SUPPORTED.items() if k != "vehicle_frame"}
        ],
    }
    bad_min = dict(good, minimum_units_per_domain_per_stratum=0)

    for payload in (bad_schema, bad_empty, bad_key, bad_min):
        path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(ValueError):
            evaluate_design_manifest([], path)


def test_tampered_design_manifest_changes_the_binding(tmp_path) -> None:
    _write_dataset(tmp_path, supported_stratum=True)
    create_split_ledger(
        tmp_path / "labels.csv",
        tmp_path / "groups.csv",
        tmp_path / "split.json",
        declared_classes=["healthy", "thrust_loss"],
    )
    manifest_path = _manifest(tmp_path, [dict(_SUPPORTED)])
    first = build_fidelity_report(
        tmp_path / "features.csv",
        tmp_path / "labels.csv",
        tmp_path / "groups.csv",
        tmp_path / "split.json",
        design_manifest_path=manifest_path,
    )
    original_sha = first["design_manifest_sha256"]

    tampered = json.loads(manifest_path.read_text(encoding="utf-8"))
    tampered["minimum_units_per_domain_per_stratum"] = 99
    manifest_path.write_text(json.dumps(tampered), encoding="utf-8")
    second = build_fidelity_report(
        tmp_path / "features.csv",
        tmp_path / "labels.csv",
        tmp_path / "groups.csv",
        tmp_path / "split.json",
        design_manifest_path=manifest_path,
    )

    assert original_sha != second["design_manifest_sha256"]
    assert second["design_manifest_sha256"] == sha256_file(manifest_path)


def test_no_synthetic_data_reports_all_required_strata_missing(tmp_path) -> None:
    import pandas as pd

    from src.constants import FEATURE_NAMES, VALID_LABELS

    _write_dataset(tmp_path)
    groups = pd.read_csv(tmp_path / "groups.csv")
    keep = groups["source_type"] == "real"
    groups[keep].to_csv(tmp_path / "groups.csv", index=False)
    pd.read_csv(tmp_path / "labels.csv")[keep.reset_index(drop=True)].to_csv(
        tmp_path / "labels.csv", index=False
    )
    pd.read_csv(tmp_path / "features.csv")[  # noqa: PD901 - positional filter
        keep.reset_index(drop=True)
    ].to_csv(tmp_path / "features.csv", index=False, columns=list(FEATURE_NAMES))
    assert VALID_LABELS  # imported for parity with dataset writer
    create_split_ledger(
        tmp_path / "labels.csv",
        tmp_path / "groups.csv",
        tmp_path / "split.json",
        declared_classes=["healthy", "thrust_loss"],
    )
    manifest_path = _manifest(tmp_path, [dict(_SUPPORTED)])

    report = build_fidelity_report(
        tmp_path / "features.csv",
        tmp_path / "labels.csv",
        tmp_path / "groups.csv",
        tmp_path / "split.json",
        design_manifest_path=manifest_path,
    )
    assert report["status"] == "blocked_no_verified_synthetic_data"
    assert report["evaluated_required_strata"] == 0
    assert report["missing_required_strata"] == 1


def test_cli_accepts_design_manifest_flag() -> None:
    from synthetic_data.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(
        [
            "fidelity",
            "--features-csv",
            "f.csv",
            "--labels-csv",
            "l.csv",
            "--groups-csv",
            "g.csv",
            "--split-ledger",
            "s.json",
            "--design-manifest",
            "d.json",
            "--output",
            "o.json",
        ]
    )
    assert args.design_manifest == "d.json"


def test_feature_fidelity_recomputes_bound_raw_temporal_evidence(tmp_path) -> None:
    import numpy as np
    import pandas as pd

    _write_dataset(
        tmp_path,
        supported_stratum=True,
        synthetic_pairs=8,
        real_per_label=20,
    )
    split = create_split_ledger(
        tmp_path / "labels.csv",
        tmp_path / "groups.csv",
        tmp_path / "split.json",
        declared_classes=["healthy", "thrust_loss"],
    )
    feature_design = _manifest(tmp_path, [dict(_SUPPORTED)], minimum=3)
    temporal_design = {
        "schema": "logdiagnosis.temporal-fidelity-design/v1",
        "candidate_manifest_sha256": "a" * 64,
        "feature_fidelity_design_sha256": sha256_file(feature_design),
        "required_strata": [dict(_SUPPORTED)],
        "required_channels": ["accel_x", "motor_cmd"],
        "channel_sources": {
            "accel_x": {
                "message_type": "IMU",
                "value_field": "AccX",
                "time_field": "TimeUS",
                "time_scale_to_sec": 0.000001,
                "value_scale": 1.0,
                "value_offset": 0.0,
                "selector": {"I": 0},
            },
            "motor_cmd": {
                "message_type": "RCOU",
                "value_field": "C1",
                "time_field": "TimeUS",
                "time_scale_to_sec": 0.000001,
                "value_scale": 1.0,
                "value_offset": 0.0,
                "selector": {},
            },
        },
        "channel_pairs": [{"one": "accel_x", "two": "motor_cmd"}],
        "acf_lags_sec": [0.1],
        "psd_bands_hz": [{"name": "low", "low_hz": 0.1, "high_hz": 2.0}],
        "minimum_lineages_per_domain_per_stratum": 8,
        "bootstrap_draws": 1000,
        "seed": 31,
        "frozen_before_evaluation": True,
        "require_transition_timing": True,
        "maximum_cross_channel_lag_sec": 0.5,
    }
    temporal_design_path = tmp_path / "temporal_design.json"
    temporal_design_path.write_text(json.dumps(temporal_design), encoding="utf-8")
    groups = pd.read_csv(tmp_path / "groups.csv").fillna("")
    real = groups[
        (groups["source_type"] == "real")
        & (groups["primary_label"] == "thrust_loss")
        & groups["source_group"].map(split["source_group_assignments"]).eq("real_train")
    ].head(8)
    synthetic = groups[
        (groups["source_type"] == "sitl") & (groups["primary_label"] == "thrust_loss")
    ].head(8)
    assert len(real) == len(synthetic) == 8
    times = np.arange(256, dtype=float) * 0.05
    one = np.sin(2 * np.pi * times)
    two = np.sin(2 * np.pi * times + 0.2)
    records = []
    for domain, frame in (("real", real), ("synthetic", synthetic)):
        for _, row in frame.iterrows():
            records.append(
                {
                    "domain": domain,
                    "lineage_root_id": row["lineage_root_id"],
                    "near_duplicate_cluster_id": row["near_duplicate_cluster_id"],
                    "source_artifact_sha256": row["sha256"],
                    "stratum": {name: row[name] for name in STRATIFIERS},
                    "transition_time_sec": 4.0,
                    "channels": {
                        "accel_x": {
                            "time_sec": times.tolist(),
                            "values": one.tolist(),
                        },
                        "motor_cmd": {
                            "time_sec": times.tolist(),
                            "values": two.tolist(),
                        },
                    },
                }
            )
    temporal_ledger = {
        "schema": "logdiagnosis.temporal-fidelity-ledger/v1",
        "candidate_manifest_sha256": "a" * 64,
        "temporal_design_sha256": sha256_file(temporal_design_path),
        "dataset": {
            "features_sha256": sha256_file(tmp_path / "features.csv"),
            "labels_sha256": sha256_file(tmp_path / "labels.csv"),
            "groups_sha256": sha256_file(tmp_path / "groups.csv"),
            "split_ledger_sha256": sha256_file(tmp_path / "split.json"),
        },
        "records": records,
    }
    temporal_ledger_path = tmp_path / "temporal_ledger.json"
    temporal_ledger_path.write_text(json.dumps(temporal_ledger), encoding="utf-8")

    report = build_fidelity_report(
        tmp_path / "features.csv",
        tmp_path / "labels.csv",
        tmp_path / "groups.csv",
        tmp_path / "split.json",
        design_manifest_path=feature_design,
        temporal_ledger_path=temporal_ledger_path,
        temporal_design_path=temporal_design_path,
    )

    assert report["raw_temporal_checks_pass"] is True
    assert report["candidate_manifest_sha256"] == "a" * 64
    assert report["raw_temporal_report"]["dataset_identity_verified"] is True
    assert report["raw_temporal_report"]["temporal_ledger_sha256"] == sha256_file(
        temporal_ledger_path
    )
