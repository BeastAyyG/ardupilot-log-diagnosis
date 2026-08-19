"""Cross-module contract and adversarial edge checks for the deterministic core."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pyarrow as pa
import pytest
from pyarrow import ipc

from src.core.causality.cita_dag import build_cita_dag
from src.core.causality.impact_boundary import detect_impact_boundary
from src.core.dynamics.welch_fft import extract_welch_psd
from src.core.dynamics.wiener_deconv import estimate_step_response, wiener_deconvolve
from src.core.ingestion.arrow_parser import parse_arrow
from src.core.ingestion.bitmask_sentinel import audit_logging
from src.core.ingestion.spline_resampler import cubic_hermite_resample
from src.core.physics.rigid_body_6dof import solve_rigid_body_6dof
from src.core.reasoning.conformal_predictor import ConformalPredictor
from src.core.reasoning.rule_matrix_44 import RULE_MATRIX_44, evaluate_rule_matrix
from src.core.remediation.param_pdef_validator import load_pdef, validate_against_pdef
from src.core.remediation.safety_clamper import clamp_parameter_changes


def _write_arrow(path: Path, table: pa.Table) -> None:
    with pa.OSFile(str(path), "wb") as sink, ipc.new_file(sink, table.schema) as writer:
        writer.write_table(table)


def test_arrow_tracks_requested_names_and_accepts_a_single_name(tmp_path: Path) -> None:
    path = tmp_path / "single.arrow"
    _write_arrow(path, pa.table({"Type": ["ATT"], "TimeUS": [1]}))

    result = parse_arrow(path, "ATT")

    assert result.requested_messages == ("ATT",)
    assert result.missing_messages == ()
    assert result.table("att").num_rows == 1


def test_spline_extrapolation_uses_boundary_tangents_and_contiguous_output() -> None:
    result = cubic_hermite_resample([0.0, 1.0, 2.0], [0.0, 1.0, 4.0], [-1.0, 0.5, 3.0], extrapolate=True)

    assert np.allclose(result, [-1.0, 0.375, 7.0])
    assert result.flags.c_contiguous


def test_sentinel_normalizes_rate_and_parameter_keys_and_skips_bad_rows() -> None:
    audit = audit_logging(
        {"gps": [{"TimeUS": "0"}, {"TimeUS": "bad"}, {"TimeUS": 1_000_000}, {"TimeUS": 10_000_000}]},
        {"log_bitmask": 0},
        expected_rates_hz={"gps": 1.0},
    )

    assert audit.findings[0].status == "dropout"
    assert audit.findings[0].count == 3


def test_ned_force_uses_default_gravity_and_rejects_empty_batches() -> None:
    result = solve_rigid_body_6dof(
        [[0.0, 0.0, 9.80665]],
        [0.0, 0.0, 0.0],
        [0.0, 0.0, 0.0],
        [[0.0, 0.0, 0.0]],
        mass_kg=np.float64(2.0),
        inertia_kg_m2=np.eye(3),
    )

    assert np.allclose(result.residual_force_body, 0.0)
    with pytest.raises(ValueError, match="at least one"):
        solve_rigid_body_6dof(
            np.empty((0, 3)),
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0],
            mass_kg=1.0,
            inertia_kg_m2=np.eye(3),
        )


def test_impact_boundary_marks_the_shock_sample_as_noise_boundary() -> None:
    times = np.arange(4, dtype=float) * 100_000
    acceleration = np.tile([0.0, 0.0, 9.80665], (4, 1))
    acceleration[2, 2] = 40.0 * 9.80665

    result = detect_impact_boundary(times, acceleration)

    assert result.detected and result.impact_index == 2
    assert result.noise_boundary_index == result.impact_index


def test_cita_accepts_numpy_scalars_and_trims_dependency_names() -> None:
    result = build_cita_dag(
        {
            "sensor": {"onset_us": np.int64(1_000), "score": np.float64(0.8)},
            "control": {"onset_us": np.int64(2_000), "score": np.float64(0.7)},
        },
        dependencies=[(" sensor ", " control ")],
    )

    assert result.edges == (("sensor", "control"),)
    assert result.root_cause == "sensor"
    assert build_cita_dag(
        {"sensor": {"onset_us": 1_000, "score": 1.0}, "control": {"onset_us": 2_000, "score": 1.0}},
        dependencies=[],
    ).edges == ()


def test_welch_rejects_fractional_segment_options_and_limits_harmonics() -> None:
    with pytest.raises(ValueError, match="nperseg"):
        extract_welch_psd(np.ones(64), 100.0, nperseg=16.5)

    times = np.arange(1_024) / 1_024.0
    result = extract_welch_psd(np.sin(2 * np.pi * 128 * times), 1_024.0, nperseg=256, max_harmonics=2)
    assert result.ins_hntch_hmncs <= 2


def test_step_metrics_report_first_stable_suffix_and_reject_no_step() -> None:
    target = np.zeros(100)
    target[10:] = 1.0
    actual = np.zeros(100)
    response = np.ones(90)
    response[:5] = [0.0, 0.2, 0.95, 1.1, 1.0]
    response[30] = 1.1
    actual[10:] = response

    metrics = estimate_step_response(target, actual, 10.0)
    assert metrics.status == "reliable"
    assert metrics.settling_time_s == pytest.approx(3.1)
    assert estimate_step_response(np.ones(100), actual, 10.0).status == "insufficient_data"


def test_core_numeric_outputs_remain_finite_and_shaped() -> None:
    rng = np.random.default_rng(7)
    for size in (8, 17, 64):
        reference = rng.normal(size=size)
        observed = rng.normal(size=size)
        impulse = wiener_deconvolve(reference, observed)
        resampled = cubic_hermite_resample(np.arange(size), reference, np.linspace(0.0, size - 1.0, size))
        assert impulse.shape == (size,)
        assert resampled.shape == (size,)
        assert np.isfinite(impulse).all() and np.isfinite(resampled).all()


def test_rules_are_unique_across_seven_subsystems_and_accept_numpy_features() -> None:
    assert len(RULE_MATRIX_44) == 44
    assert len({rule.rule_id for rule in RULE_MATRIX_44}) == 44
    assert len({rule.subsystem for rule in RULE_MATRIX_44}) == 7
    findings = evaluate_rule_matrix({"vibe_z_max": np.float32(31.0)})
    assert [finding.rule_id for finding in findings] == ["S04"]


def test_pdef_reads_child_fields_and_enums_and_rejects_nonfinite_values(tmp_path: Path) -> None:
    path = tmp_path / "nested.pdef.xml"
    path.write_text(
        "<params><param name='GAIN'><field type='float' range='-1 1'/></param>"
        "<param name='MODE'><field type='enum'/><value code='0'/><value code='AUTO'/></param></params>",
        encoding="utf-8",
    )

    definitions = load_pdef(path)
    issues = validate_against_pdef({"GAIN": np.nan, "MODE": "BAD", "UNKNOWN": 1}, definitions)

    assert definitions["GAIN"].minimum == -1.0
    assert definitions["MODE"].enum_values == ("0", "AUTO")
    assert [(issue.name, issue.kind) for issue in issues] == [
        ("GAIN", "finite"),
        ("MODE", "enum"),
        ("UNKNOWN", "unknown"),
    ]


def test_safety_clamp_handles_numpy_and_negative_baselines() -> None:
    result = clamp_parameter_changes(
        {"NEGATIVE": np.int64(-100), "ZERO": 0.0},
        {"NEGATIVE": np.float64(-150), "ZERO": 1.0},
    )

    assert result.changes[0].clamped == -125.0
    assert result.changes[0].was_clamped
    assert result.changes[1].clamped == 0.0


class _UnsortedModel:
    classes_ = np.array([2, 0])

    def predict_proba(self, features: object) -> np.ndarray:
        return np.asarray(features, dtype=float)


def test_conformal_handles_unsorted_classes_and_rejects_unnormalized_probabilities() -> None:
    predictor = ConformalPredictor(_UnsortedModel()).fit([[0.9, 0.1], [0.1, 0.9]], [2, 0])
    assert predictor.predict_sets([[0.8, 0.2]])[0]
    with pytest.raises(ValueError, match="sum to one"):
        predictor.predict_sets([[0.8, 0.3]])
