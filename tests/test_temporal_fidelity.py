"""Raw temporal fidelity producer and tamper/failure paths."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from synthetic_data.schema import sha256_file
from synthetic_data.temporal_fidelity import (
    build_temporal_fidelity_report,
    validate_temporal_fidelity_report,
)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _write_inputs(
    root: Path,
    *,
    synthetic_cadence_scale: float = 1.0,
    synthetic_count: int = 8,
) -> tuple[Path, Path, dict[str, Path]]:
    feature_design = root / "feature_design.json"
    feature_design.write_text('{"frozen":true}\n', encoding="utf-8")
    temporal_design = {
        "schema": "logdiagnosis.temporal-fidelity-design/v1",
        "candidate_manifest_sha256": "a" * 64,
        "feature_fidelity_design_sha256": sha256_file(feature_design),
        "required_strata": [
            {
                "primary_label": "thrust_loss",
                "flight_phase": "hover",
                "vehicle_frame": "quad",
                "firmware_commit": "Copter-4.6.2",
                "simulation_family": "thrust_loss",
            }
        ],
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
        "acf_lags_sec": [0.1, 0.5],
        "psd_bands_hz": [
            {"name": "low", "low_hz": 0.1, "high_hz": 2.0},
            {"name": "mid", "low_hz": 2.0, "high_hz": 4.0},
        ],
        "minimum_lineages_per_domain_per_stratum": 8,
        "bootstrap_draws": 1000,
        "seed": 19,
        "frozen_before_evaluation": True,
        "require_transition_timing": True,
        "maximum_cross_channel_lag_sec": 0.5,
    }
    design_path = root / "temporal_design.json"
    design_path.write_text(json.dumps(temporal_design), encoding="utf-8")

    records = []

    def add(domain: str, index: int) -> None:
        scale = synthetic_cadence_scale if domain == "synthetic" else 1.0
        times = np.arange(256, dtype=float) * 0.05 * scale
        phase = index * 0.03
        accel = np.sin(2 * np.pi * 1.0 * times / scale + phase)
        motor = np.sin(2 * np.pi * 1.0 * times / scale + phase + 0.2)
        family = "thrust_loss" if domain == "synthetic" else "physical"
        records.append(
            {
                "domain": domain,
                "lineage_root_id": f"{domain}-lineage-{index}",
                "near_duplicate_cluster_id": f"{domain}-cluster-{index}",
                "source_artifact_sha256": _digest(f"{domain}-artifact-{index}"),
                "stratum": {
                    "primary_label": "thrust_loss",
                    "flight_phase": "hover",
                    "vehicle_frame": "quad",
                    "firmware_commit": "Copter-4.6.2",
                    "simulation_family": family,
                },
                "transition_time_sec": 4.0 + index * 0.1,
                "channels": {
                    "accel_x": {
                        "time_sec": times.tolist(),
                        "values": accel.tolist(),
                    },
                    "motor_cmd": {
                        "time_sec": times.tolist(),
                        "values": motor.tolist(),
                    },
                },
            }
        )

    for index in range(8):
        add("real", index)
    for index in range(synthetic_count):
        add("synthetic", index)
    dataset_paths = {
        "features_csv": root / "features.csv",
        "labels_csv": root / "labels.csv",
        "groups_csv": root / "groups.csv",
        "split_ledger_path": root / "split.json",
    }
    dataset_paths["features_csv"].write_text("feature\n0\n", encoding="utf-8")
    dataset_paths["labels_csv"].write_text("label\n0\n", encoding="utf-8")
    dataset_paths["split_ledger_path"].write_text(
        '{"schema":"test-split"}\n', encoding="utf-8"
    )
    pd.DataFrame(
        [
            {
                "lineage_root_id": record["lineage_root_id"],
                "source_type": ("real" if record["domain"] == "real" else "sitl"),
                "sha256": record["source_artifact_sha256"],
                "near_duplicate_cluster_id": record["near_duplicate_cluster_id"],
                "verification_status": (
                    "" if record["domain"] == "real" else "accepted"
                ),
                **record["stratum"],
            }
            for record in records
        ]
    ).to_csv(dataset_paths["groups_csv"], index=False)
    ledger = {
        "schema": "logdiagnosis.temporal-fidelity-ledger/v1",
        "candidate_manifest_sha256": "a" * 64,
        "temporal_design_sha256": sha256_file(design_path),
        "dataset": {
            "features_sha256": sha256_file(dataset_paths["features_csv"]),
            "labels_sha256": sha256_file(dataset_paths["labels_csv"]),
            "groups_sha256": sha256_file(dataset_paths["groups_csv"]),
            "split_ledger_sha256": sha256_file(dataset_paths["split_ledger_path"]),
        },
        "records": records,
    }
    ledger_path = root / "temporal_ledger.json"
    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
    return ledger_path, design_path, dataset_paths


def test_temporal_report_derives_complete_signal_family(tmp_path) -> None:
    ledger, design, dataset = _write_inputs(tmp_path)

    report = build_temporal_fidelity_report(ledger, design, **dataset)

    assert report["complete"] is True
    assert report["raw_temporal_checks_pass"] is True
    assert report["near_duplicate_audit_pass"] is True
    assert report["real_lineages"] == 8
    assert report["synthetic_lineages"] == 8
    assert report["bootstrap_draws"] == 1000
    names = set(report["metric_names"])
    assert "channel:accel_x:sample_rate_hz" in names
    assert "channel:accel_x:acf:0.1s" in names
    assert "channel:accel_x:psd_fraction:low" in names
    assert "pair:accel_x|motor_cmd:coherence:low" in names
    assert "pair:accel_x|motor_cmd:cross_correlation_lag_sec" in names
    assert "transition_time_sec" in names
    assert report["release_authorized"] is False
    assert report["accuracy_claim"] == "not_demonstrated"


def test_changed_synthetic_cadence_fails_real_real_envelope(tmp_path) -> None:
    ledger, design, dataset = _write_inputs(tmp_path, synthetic_cadence_scale=2.0)

    report = build_temporal_fidelity_report(ledger, design, **dataset)

    assert report["complete"] is True
    assert report["raw_temporal_checks_pass"] is False
    sample_rate = report["strata"][0]["metrics"]["channel:accel_x:sample_rate_hz"]
    assert sample_rate["real_median"] == pytest.approx(20.0)
    assert sample_rate["synthetic_median"] == pytest.approx(10.0)


def test_under_supported_temporal_stratum_is_explicitly_blocked(tmp_path) -> None:
    ledger, design, dataset = _write_inputs(tmp_path, synthetic_count=7)

    report = build_temporal_fidelity_report(ledger, design, **dataset)

    assert report["complete"] is False
    assert report["raw_temporal_checks_pass"] is False
    assert report["missing_strata"] == 1


def test_near_duplicate_cluster_crossing_lineages_is_rejected(tmp_path) -> None:
    ledger_path, design, dataset = _write_inputs(tmp_path)
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger["records"][1]["near_duplicate_cluster_id"] = ledger["records"][0][
        "near_duplicate_cluster_id"
    ]
    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")

    with pytest.raises(ValueError, match="near-duplicate"):
        build_temporal_fidelity_report(ledger_path, design, **dataset)


def test_temporal_record_must_match_bound_groups_provenance(tmp_path) -> None:
    ledger_path, design, dataset = _write_inputs(tmp_path)
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger["records"][0]["source_artifact_sha256"] = "f" * 64
    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")

    with pytest.raises(ValueError, match="groups CSV"):
        build_temporal_fidelity_report(ledger_path, design, **dataset)


def test_temporal_report_tamper_fails_exact_recomputation(tmp_path) -> None:
    ledger, design, dataset = _write_inputs(tmp_path)
    report_path = tmp_path / "report.json"
    build_temporal_fidelity_report(ledger, design, output_path=report_path, **dataset)
    supplied = json.loads(report_path.read_text(encoding="utf-8"))
    supplied["raw_temporal_checks_pass"] = False
    report_path.write_text(json.dumps(supplied), encoding="utf-8")

    with pytest.raises(ValueError, match="exact recomputation"):
        validate_temporal_fidelity_report(report_path, ledger, design, **dataset)


def test_cli_exposes_temporal_producer_and_feature_binding() -> None:
    from synthetic_data.cli import build_parser

    parser = build_parser()
    temporal = parser.parse_args(
        [
            "temporal-fidelity",
            "--ledger",
            "raw.json",
            "--design",
            "design.json",
            "--features-csv",
            "features.csv",
            "--labels-csv",
            "labels.csv",
            "--groups-csv",
            "groups.csv",
            "--split-ledger",
            "split.json",
            "--output",
            "report.json",
        ]
    )
    assert temporal.command == "temporal-fidelity"
    fidelity = parser.parse_args(
        [
            "fidelity",
            "--features-csv",
            "features.csv",
            "--labels-csv",
            "labels.csv",
            "--groups-csv",
            "groups.csv",
            "--split-ledger",
            "split.json",
            "--design-manifest",
            "feature-design.json",
            "--temporal-ledger",
            "raw.json",
            "--temporal-design",
            "temporal-design.json",
            "--output",
            "fidelity.json",
        ]
    )
    assert fidelity.temporal_ledger == "raw.json"
    assert fidelity.temporal_design == "temporal-design.json"
