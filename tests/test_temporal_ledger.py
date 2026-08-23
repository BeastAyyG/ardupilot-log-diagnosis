"""Deterministic raw-log extraction into the temporal fidelity ledger."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from synthetic_data.schema import sha256_file
from synthetic_data.temporal_ledger import build_temporal_ledger


def _design(root: Path) -> Path:
    feature_design = root / "feature-design.json"
    feature_design.write_text("{}\n", encoding="utf-8")
    payload = {
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
                "value_scale": 2.0,
                "value_offset": 1.0,
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
        "seed": 8,
        "frozen_before_evaluation": True,
        "require_transition_timing": True,
        "maximum_cross_channel_lag_sec": 0.5,
    }
    path = root / "temporal-design.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _inputs(root: Path, monkeypatch) -> tuple[Path, Path, dict[str, Path]]:
    logs = root / "logs"
    logs.mkdir()
    real_log = logs / "real.BIN"
    synthetic_log = logs / "synthetic.BIN"
    real_log.write_bytes(b"real temporal payload")
    synthetic_log.write_bytes(b"synthetic temporal payload")
    rows = []
    for domain, path, family in (
        ("real", real_log, "physical"),
        ("sitl", synthetic_log, "thrust_loss"),
    ):
        rows.append(
            {
                "source_log": path.name,
                "source_group": f"group:{domain}",
                "lineage_root_id": f"lineage:{domain}",
                "primary_label": "thrust_loss",
                "source_type": domain,
                "verification_status": "" if domain == "real" else "accepted",
                "sha256": sha256_file(path),
                "near_duplicate_cluster_id": f"cluster:{domain}",
                "fault_onset_sec": 4.0,
                "flight_phase": "hover",
                "vehicle_frame": "quad",
                "firmware_commit": "Copter-4.6.2",
                "simulation_family": family,
            }
        )
    paths = {
        "features_csv": root / "features.csv",
        "labels_csv": root / "labels.csv",
        "groups_csv": root / "groups.csv",
        "split_ledger_path": root / "split.json",
    }
    paths["features_csv"].write_text("feature\n0\n", encoding="utf-8")
    paths["labels_csv"].write_text("label\n0\n", encoding="utf-8")
    paths["split_ledger_path"].write_text("{}\n", encoding="utf-8")
    pd.DataFrame(rows).to_csv(paths["groups_csv"], index=False)
    monkeypatch.setattr(
        "synthetic_data.temporal_ledger.load_and_validate_ledger",
        lambda *_args, **_kwargs: {
            "source_group_assignments": {"group:real": "real_train"}
        },
    )
    return logs, _design(root), paths


class _FakeParser:
    def __init__(self, _path: str):
        pass

    def parse(self) -> dict:
        imu = []
        motors = []
        for index in range(32):
            timestamp = index * 50_000
            imu.append({"TimeUS": timestamp, "I": 0, "AccX": float(index)})
            imu.append({"TimeUS": timestamp, "I": 1, "AccX": 9999.0})
            motors.append({"TimeUS": timestamp, "C1": 1200.0 + index})
        return {
            "metadata": {"parse_complete": True, "parse_error": None},
            "messages": {"IMU": imu, "RCOU": motors},
        }


def test_temporal_ledger_extracts_frozen_channels_and_scales(
    tmp_path, monkeypatch
) -> None:
    logs, design, paths = _inputs(tmp_path, monkeypatch)

    ledger = build_temporal_ledger(
        design,
        logs,
        parser_factory=_FakeParser,
        **paths,
    )

    assert ledger["candidate_manifest_sha256"] == "a" * 64
    assert len(ledger["records"]) == 2
    real = next(row for row in ledger["records"] if row["domain"] == "real")
    accel = real["channels"]["accel_x"]
    assert accel["time_sec"][1] == pytest.approx(0.05)
    assert accel["values"][0] == pytest.approx(1.0)
    assert accel["values"][1] == pytest.approx(3.0)
    assert max(accel["values"]) < 1000
    assert real["transition_time_sec"] == 4.0


def test_temporal_ledger_rejects_raw_hash_mismatch(tmp_path, monkeypatch) -> None:
    logs, design, paths = _inputs(tmp_path, monkeypatch)
    (logs / "real.BIN").write_bytes(b"tampered")

    with pytest.raises(ValueError, match="hash differs"):
        build_temporal_ledger(
            design,
            logs,
            parser_factory=_FakeParser,
            **paths,
        )


def test_temporal_ledger_refuses_path_escape(tmp_path, monkeypatch) -> None:
    logs, design, paths = _inputs(tmp_path, monkeypatch)
    groups = pd.read_csv(paths["groups_csv"])
    outside = tmp_path / "outside.BIN"
    outside.write_bytes(b"outside")
    groups.loc[0, "source_log"] = "../outside.BIN"
    groups.loc[0, "sha256"] = hashlib.sha256(b"outside").hexdigest()
    groups.to_csv(paths["groups_csv"], index=False)

    with pytest.raises(ValueError, match="escapes"):
        build_temporal_ledger(
            design,
            logs,
            parser_factory=_FakeParser,
            **paths,
        )
