"""Tests for preregistered design mathematics and stopping rules."""

from __future__ import annotations

import math

import pytest

from synthetic_data.design import (
    MANIFESTATION_FAILURE_BOUND,
    PARSER_SHAM_FAILURE_BOUND,
    binomial_tail_at_most,
    bind_design_to_inputs,
    build_experiment_design,
    sample_size_for_upper_bound,
    sequential_stopping_decision,
    zero_failure_sample_size,
)


def test_repository_gate_conventions_are_reproduced_exactly() -> None:
    assert (
        zero_failure_sample_size(
            confidence=0.95, failure_bound=MANIFESTATION_FAILURE_BOUND
        )
        == 59
    )
    assert (
        zero_failure_sample_size(
            confidence=0.95, failure_bound=PARSER_SHAM_FAILURE_BOUND
        )
        == 299
    )
    assert (
        sample_size_for_upper_bound(
            confidence=0.95, failure_bound=MANIFESTATION_FAILURE_BOUND
        )
        == 59
    )
    assert (
        sample_size_for_upper_bound(
            confidence=0.95, failure_bound=PARSER_SHAM_FAILURE_BOUND
        )
        == 299
    )


def test_binomial_tail_matches_closed_form_and_is_monotone() -> None:
    # Zero-failure tail equals the closed form used by the gate.
    for total in (59, 299):
        assert math.isclose(
            binomial_tail_at_most(failures=0, total=total, true_rate=0.01),
            0.99**total,
            rel_tol=1e-12,
        )
    values = [
        binomial_tail_at_most(failures=f, total=299, true_rate=0.01) for f in range(8)
    ]
    assert all(a < b for a, b in zip(values, values[1:]))
    # At the preregistered zero-failure target, the null tail sits just under
    # the 5% tolerance; any observed failure pushes past every budget.
    assert values[0] <= 0.05
    with pytest.raises(ValueError):
        binomial_tail_at_most(failures=5, total=3, true_rate=0.1)


def test_allowed_failures_enlarge_the_target_monotonically() -> None:
    base = sample_size_for_upper_bound(confidence=0.95, failure_bound=0.01)
    one = sample_size_for_upper_bound(
        confidence=0.95, failure_bound=0.01, allowed_failures=1
    )
    two = sample_size_for_upper_bound(
        confidence=0.95, failure_bound=0.01, allowed_failures=2
    )
    assert base < one < two
    # The enlarged target must actually deliver <=5% tail at its budget.
    assert binomial_tail_at_most(failures=2, total=two, true_rate=0.01) <= 0.05


def test_stopping_rule_transitions() -> None:
    common = dict(target_total=10, allowed_failures=0)
    assert (
        sequential_stopping_decision(completed=4, failures=0, **common)["decision"]
        == "continue"
    )
    stopped = sequential_stopping_decision(completed=10, failures=0, **common)
    assert stopped["decision"] == "stop_pass"
    failed = sequential_stopping_decision(completed=3, failures=1, **common)
    assert failed["decision"] == "stop_fail"
    budgeted = sequential_stopping_decision(
        target_total=10, completed=3, failures=1, allowed_failures=1
    )
    assert budgeted["decision"] == "continue"
    with pytest.raises(ValueError):
        sequential_stopping_decision(target_total=5, completed=6, failures=0)
    with pytest.raises(ValueError):
        sequential_stopping_decision(target_total=5, completed=3, failures=4)


def test_design_manifest_freezes_commitments(tmp_path) -> None:
    design = build_experiment_design(
        declared_classes=["healthy", "thrust_loss"],
        required_scenarios=["thrust_loss"],
        confirmation_cohort_sha256="c" * 64,
        output_path=tmp_path / "design.json",
    )
    assert design["required_manifestation_units_per_scenario"] == 59
    assert design["required_parser_sham_units"] == 299
    assert list(design["dose_grid"]) == [0.1, 0.25, 0.5, 1.0, 2.0]
    assert "never revisit the development test" in design["selection_rule"]
    assert "blinded physical confirmation" in design["claim_rule"]

    again = build_experiment_design(
        declared_classes=["healthy", "thrust_loss"],
        required_scenarios=["thrust_loss"],
        confirmation_cohort_sha256="c" * 64,
    )
    from synthetic_data.schema import canonical_json_bytes

    import hashlib

    def h(d):
        return hashlib.sha256(canonical_json_bytes(d)).hexdigest()

    assert h(design) == h(again)  # deterministic preregistration

    with pytest.raises(ValueError, match="duplicates"):
        build_experiment_design(
            declared_classes=["healthy", "healthy"],
            required_scenarios=["thrust_loss"],
            confirmation_cohort_sha256="c" * 64,
        )


def test_design_binding_covers_inputs(tmp_path) -> None:
    input_a = tmp_path / "a.json"
    input_a.write_text("{}", encoding="utf-8")
    design = build_experiment_design(
        declared_classes=["healthy"],
        required_scenarios=["thrust_loss"],
        confirmation_cohort_sha256="c" * 64,
        input_hashes={"a": "a" * 64},
    )
    first = bind_design_to_inputs(design, input_a)
    input_a.write_text('{"x":1}', encoding="utf-8")
    second = bind_design_to_inputs(design, input_a)
    assert first != second

    with pytest.raises(ValueError, match="malformed"):
        build_experiment_design(
            declared_classes=["healthy"],
            required_scenarios=["thrust_loss"],
            confirmation_cohort_sha256="c" * 64,
            input_hashes={"a": "nothex"},
        )


def test_dose_grid_validation() -> None:
    with pytest.raises(ValueError, match="dose grid"):
        build_experiment_design(
            declared_classes=["healthy"],
            required_scenarios=["s"],
            confirmation_cohort_sha256="c" * 64,
            dose_grid=(0.0,),
        )
