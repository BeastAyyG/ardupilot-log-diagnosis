"""Randomization-layer planning guarantees for paired SITL runs."""

from __future__ import annotations

import math

import pytest

from synthetic_data.planner import (
    _safe_plan,
    build_paired_run_plans,
)
from synthetic_data.randomization import CATALOG_BY_NAME, RANDOMIZATION_CATALOG
from synthetic_data.schema import ParameterSchema
from tests.test_sitl_data_factory import COMMIT, _schema

CATALOG_NAMES = tuple(spec.name for spec in RANDOMIZATION_CATALOG)


def _full_schema() -> ParameterSchema:
    return _schema("SIM_ENGINE_FAIL", "SIM_ENGINE_MUL", *CATALOG_NAMES)


def test_randomized_pairs_share_identical_parameter_draws() -> None:
    plans = build_paired_run_plans(
        1,
        seed=20260880,
        ardupilot_revision=COMMIT,
        scenarios=["motor_imbalance"],
        parameter_schema=_full_schema(),
        randomization_enabled=True,
    )
    assert len(plans) == 2
    control, fault = plans
    assert control["randomization_parameters"] == fault["randomization_parameters"]
    assert fault["randomization_parameters"], "catalog must apply to a full schema"
    for name, value in fault["randomization_parameters"].items():
        spec = CATALOG_BY_NAME[name]
        assert spec.low <= value <= spec.high
        assert math.isfinite(value)
        # Both members boot with the identical latent vehicle.
        assert control["startup_parameters"][name] == value
        assert fault["startup_parameters"][name] == value


def test_randomization_draw_is_deterministic_per_seed() -> None:
    first = build_paired_run_plans(
        1,
        seed=20260881,
        ardupilot_revision=COMMIT,
        scenarios=["motor_imbalance"],
        parameter_schema=_full_schema(),
        randomization_enabled=True,
    )
    second = build_paired_run_plans(
        1,
        seed=20260881,
        ardupilot_revision=COMMIT,
        scenarios=["motor_imbalance"],
        parameter_schema=_full_schema(),
        randomization_enabled=True,
    )
    assert first[0]["randomization_parameters"] == second[0]["randomization_parameters"]
    assert first[1]["randomization_parameters"] == second[1]["randomization_parameters"]


def test_disabled_randomization_matches_legacy_plan_shape() -> None:
    plans = build_paired_run_plans(
        1,
        seed=20260882,
        ardupilot_revision=COMMIT,
        scenarios=["motor_imbalance"],
        parameter_schema=_full_schema(),
    )
    for plan in plans:
        assert plan["randomization_parameters"] == {}
        for name in CATALOG_NAMES:
            assert name not in plan["startup_parameters"]


def test_missing_catalog_parameters_are_skipped_not_guessed() -> None:
    partial = _schema(
        "SIM_ENGINE_FAIL",
        "SIM_ENGINE_MUL",
        "SIM_GYR1_RND",
        "SIM_BATT_CAP_AH",
    )
    plans = build_paired_run_plans(
        1,
        seed=20260883,
        ardupilot_revision=COMMIT,
        scenarios=["motor_imbalance"],
        parameter_schema=partial,
        randomization_enabled=True,
    )
    drawn = set(plans[1]["randomization_parameters"])
    assert drawn == {"SIM_GYR1_RND", "SIM_BATT_CAP_AH"}


def test_randomization_changes_the_run_identity() -> None:
    plain = build_paired_run_plans(
        1,
        seed=20260884,
        ardupilot_revision=COMMIT,
        scenarios=["motor_imbalance"],
        parameter_schema=_full_schema(),
    )
    randomized = build_paired_run_plans(
        1,
        seed=20260884,
        ardupilot_revision=COMMIT,
        scenarios=["motor_imbalance"],
        parameter_schema=_full_schema(),
        randomization_enabled=True,
    )
    assert plain[0]["run_fingerprint"] != randomized[0]["run_fingerprint"]
    assert plain[1]["run_fingerprint"] != randomized[1]["run_fingerprint"]
    # Same seed keeps the human-readable identity stable; the immutable
    # fingerprint is what carries the randomized latent vehicle.
    assert plain[1]["run_id"] == randomized[1]["run_id"]


def test_safe_plan_accepts_and_rejects_randomization_payloads() -> None:
    (control, fault) = build_paired_run_plans(
        1,
        seed=20260885,
        ardupilot_revision=COMMIT,
        scenarios=["motor_imbalance"],
        parameter_schema=_full_schema(),
        randomization_enabled=True,
    )
    _safe_plan(control)
    _safe_plan(fault)

    corrupted = {
        **fault,
        "randomization_parameters": {**fault["randomization_parameters"], "SIM_MAG_RND": float("nan")},
    }
    with pytest.raises(ValueError, match="non-finite randomized"):
        _safe_plan(corrupted)

    not_a_mapping = {**control, "randomization_parameters": ["SIM_MAG_RND"]}
    with pytest.raises(ValueError, match="invalid randomization_parameters"):
        _safe_plan(not_a_mapping)


def test_verify_tool_flags_present_and_missing_parameters(tmp_path) -> None:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from ops.intervention.verify_randomization_params import verify_inventory

    values = {"SIM_GYR1_RND": 0.0, "UNRELATED": 1.0}
    report = verify_inventory(values)
    assert report["verified_count"] == 1
    assert "SIM_GYR2_RND" in report["missing_parameters"]
    assert "SIM_ACC1_RND" in report["missing_parameters"]
    entry = report["parameters"]["SIM_GYR1_RND"]
    assert entry["present"] is True
    assert entry["captured_baseline"] == 0.0
    missing_entry = report["parameters"]["SIM_ACC1_RND"]
    assert missing_entry["present"] is False
    assert missing_entry["captured_baseline"] is None


def test_derived_baro_allowances_declared_and_shared_by_pair() -> None:
    plans = build_paired_run_plans(
        1,
        seed=20260900,
        ardupilot_revision=COMMIT,
        scenarios=["motor_imbalance"],
        parameter_schema=_full_schema(),
        randomization_enabled=True,
    )
    control, fault = plans
    for plan in (control, fault):
        allowances = plan["derived_parameter_allowances"]
        assert set(allowances) == {"BARO1_GND_PRESS", "BARO2_GND_PRESS"}
        for parameter, spec in allowances.items():
            assert spec["because"] == "SIM_BARO_RND"
            low, high = spec["range"]
            assert 30000.0 <= low < high <= 120000.0
    assert (
        control["derived_parameter_allowances"]
        == fault["derived_parameter_allowances"]
    )


def test_disabled_randomization_declares_no_allowances() -> None:
    plans = build_paired_run_plans(
        1,
        seed=20260901,
        ardupilot_revision=COMMIT,
        scenarios=["motor_imbalance"],
        parameter_schema=_full_schema(),
    )
    for plan in plans:
        assert plan["derived_parameter_allowances"] == {}


def test_validate_live_parameters_tolerates_only_declared_baro_drift() -> None:
    from synthetic_data.executor import _validate_live_parameters

    schema = _schema(
        "BARO1_GND_PRESS",
        "BARO2_GND_PRESS",
        "SIM_ENGINE_FAIL",
        "SIM_ENGINE_MUL",
        "SIM_GYR1_RND",
        "SIM_ACC1_RND",
        "SIM_MAG_RND",
        "SIM_GPS1_NOISE",
        "SIM_VIB_MOT_MAX",
        "SIM_BATT_CAP_AH",
    )
    plan = {
        "frame": "quad",
        "startup_parameters": {"FRAME_CLASS": 1.0},
        "injection_parameters": {},
        "injection_baseline_parameters": {},
        "motor_output_parameters": {},
        "derived_parameter_allowances": {
            "BARO1_GND_PRESS": {
                "because": "SIM_BARO_RND",
                "range": [30000.0, 120000.0],
            }
        },
    }
    live = {name: float(value) for name, value in schema.parameters.items()}
    live["BARO1_GND_PRESS"] = 101234.5
    result = _validate_live_parameters(live, schema, plan)
    assert result["readbacks"]["derived:BARO1_GND_PRESS"] == 101234.5

    live["BARO1_GND_PRESS"] = 500.0
    with pytest.raises(RuntimeError, match="BARO1_GND_PRESS"):
        _validate_live_parameters(live, schema, plan)

    unexplained_plan = dict(plan)
    unexplained_plan["derived_parameter_allowances"] = {}
    live["BARO1_GND_PRESS"] = 101234.5
    with pytest.raises(RuntimeError, match="BARO1_GND_PRESS"):
        _validate_live_parameters(live, schema, unexplained_plan)


def test_safe_plan_rejects_invalid_allowance_payloads() -> None:
    from synthetic_data.planner import _safe_plan

    plans = build_paired_run_plans(
        1,
        seed=20260902,
        ardupilot_revision=COMMIT,
        scenarios=["motor_imbalance"],
        parameter_schema=_full_schema(),
        randomization_enabled=True,
    )
    bad_range = dict(plans[1])
    bad_range["derived_parameter_allowances"] = {
        "BARO1_GND_PRESS": {"because": "SIM_BARO_RND", "range": [1.0]}
    }
    with pytest.raises(ValueError, match="invalid allowance"):
        _safe_plan(bad_range)
    non_dict = dict(plans[0])
    non_dict["derived_parameter_allowances"] = ["BARO1_GND_PRESS"]
    with pytest.raises(ValueError, match="invalid derived_parameter_allowances"):
        _safe_plan(non_dict)
