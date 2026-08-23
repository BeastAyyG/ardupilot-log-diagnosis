"""Preregistered sample-size, stopping-rule, and design-manifest mathematics.

The numbers this module emits are commitments, not estimates: they reproduce
the repository's one-sided zero-failure gate convention exactly (59 fault-
manifestation units per scenario for a 5% failure bound, 299 sham/parser
units for a 1% bound, both at 95% one-sided confidence). Nothing here can be
satisfied by development data.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from .schema import sha256_file

DESIGN_SCHEMA = "logdiagnosis.experiment-design-manifest/v1"
DEFAULT_CONFIDENCE = 0.95
MANIFESTATION_FAILURE_BOUND = 0.05
PARSER_SHAM_FAILURE_BOUND = 0.01
DEFAULT_DOSE_GRID = (0.1, 0.25, 0.5, 1.0, 2.0)


def _validate_confidence(confidence: float) -> None:
    if isinstance(confidence, bool) or not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be strictly between 0 and 1")


def _validate_bound(bound: float) -> None:
    if isinstance(bound, bool) or not 0.0 < bound < 1.0:
        raise ValueError("failure bound must be strictly between 0 and 1")


def binomial_tail_at_most(*, failures: int, total: int, true_rate: float) -> float:
    """P(X <= failures) for X ~ Binomial(total, true_rate), computed exactly."""

    if total < 0 or failures < 0 or failures > total:
        raise ValueError("invalid failure/total counts")
    if isinstance(true_rate, bool) or not 0.0 <= true_rate <= 1.0:
        raise ValueError("true_rate must be within [0, 1]")
    if true_rate == 0.0:
        return 1.0
    if true_rate == 1.0:
        return 1.0 if failures >= total else 0.0
    # term_k = C(total, k) p^k (1-p)^(total-k), built by stable recurrence
    # from term_0 so no logarithms or large intermediates are needed.
    term = (1.0 - true_rate) ** total
    tail = term
    for count in range(1, failures + 1):
        term *= (total - count + 1) / count * (true_rate / (1.0 - true_rate))
        tail += term
    return min(1.0, tail)


def sample_size_for_upper_bound(
    *,
    confidence: float = DEFAULT_CONFIDENCE,
    failure_bound: float,
    allowed_failures: int = 0,
) -> int:
    """Smallest n with P(X <= allowed_failures | p=failure_bound) <= 1-confidence."""

    _validate_confidence(confidence)
    _validate_bound(failure_bound)
    if isinstance(allowed_failures, bool) or allowed_failures < 0:
        raise ValueError("allowed_failures must be a non-negative integer")
    tolerance = 1.0 - confidence
    candidate = max(1, allowed_failures)
    while (
        binomial_tail_at_most(
            failures=allowed_failures, total=candidate, true_rate=failure_bound
        )
        > tolerance
    ):
        candidate += 1
        if candidate > 10_000_000:
            raise ValueError("sample-size search did not converge")
    return candidate


def zero_failure_sample_size(
    *,
    confidence: float = DEFAULT_CONFIDENCE,
    failure_bound: float,
) -> int:
    """Closed form used when no failures may occur: ln(1-c)/ln(1-b)."""

    _validate_confidence(confidence)
    _validate_bound(failure_bound)
    return math.ceil(math.log(1.0 - confidence) / math.log(1.0 - failure_bound))


def sequential_stopping_decision(
    *,
    target_total: int,
    completed: int,
    failures: int,
    allowed_failures: int = 0,
) -> dict[str, Any]:
    """Fail-closed sequential rule over an immutable, preregistered target."""

    for name, value in (
        ("target_total", target_total),
        ("completed", completed),
        ("failures", failures),
        ("allowed_failures", allowed_failures),
    ):
        if isinstance(value, bool) or value < 0:
            raise ValueError(f"{name} must be a non-negative integer")
    if completed > target_total:
        raise ValueError("completed exceeds the preregistered target")
    if failures > completed:
        raise ValueError("failures exceed completed runs")
    if failures > allowed_failures:
        return {
            "decision": "stop_fail",
            "remaining_required": 0,
            "reason": "failure budget exhausted",
        }
    remaining = target_total - completed
    if remaining == 0:
        return {
            "decision": "stop_pass",
            "remaining_required": 0,
            "reason": "preregistered target met within budget",
        }
    return {
        "decision": "continue",
        "remaining_required": remaining,
        "reason": "target not yet met",
    }


def build_experiment_design(
    *,
    declared_classes: list[str],
    required_scenarios: list[str],
    confirmation_cohort_sha256: str,
    manifestation_units_per_scenario: int | None = None,
    parser_sham_units: int | None = None,
    confidence: float = DEFAULT_CONFIDENCE,
    dose_grid: tuple[float, ...] = DEFAULT_DOSE_GRID,
    input_hashes: dict[str, str] | None = None,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    """Emit the frozen design every later stage must consume unchanged."""

    if not declared_classes or not required_scenarios:
        raise ValueError("design requires classes and scenarios")
    if len(set(declared_classes)) != len(declared_classes):
        raise ValueError("declared classes contain duplicates")
    if len(set(required_scenarios)) != len(required_scenarios):
        raise ValueError("required scenarios contain duplicates")
    for dose in dose_grid:
        if isinstance(dose, bool) or not 0.0 < dose <= 2.0:
            raise ValueError("dose grid entries must lie in (0, 2]")
    if input_hashes:
        invalid = [k for k, v in input_hashes.items() if not _is_sha256(v)]
        if invalid:
            raise ValueError(f"input hashes malformed: {sorted(invalid)}")

    manifestation_units = (
        manifestation_units_per_scenario
        or sample_size_for_upper_bound(
            confidence=confidence, failure_bound=MANIFESTATION_FAILURE_BOUND
        )
    )
    parser_units = parser_sham_units or sample_size_for_upper_bound(
        confidence=confidence, failure_bound=PARSER_SHAM_FAILURE_BOUND
    )
    design = {
        "schema": DESIGN_SCHEMA,
        "confidence_one_sided": confidence,
        "manifestation_failure_bound": MANIFESTATION_FAILURE_BOUND,
        "parser_sham_failure_bound": PARSER_SHAM_FAILURE_BOUND,
        "required_manifestation_units_per_scenario": manifestation_units,
        "required_parser_sham_units": parser_units,
        "declared_classes": list(declared_classes),
        "required_scenarios": list(required_scenarios),
        "dose_grid": [float(dose) for dose in dose_grid],
        "confirmation_cohort_sha256": confirmation_cohort_sha256,
        "selection_rule": (
            "select one candidate once on real train/calibration/development "
            "partitions; never revisit the development test"
        ),
        "stopping_rule": (
            "sequential fail-closed: any failure beyond the allowed budget "
            "stops the arm; the target total is never enlarged post hoc"
        ),
        "claim_rule": (
            "no accuracy claim without a new blinded physical confirmation "
            "cohort meeting every acceptance gate"
        ),
    }
    if input_hashes:
        design["input_hashes"] = dict(sorted(input_hashes.items()))
    if output_path:
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(design, indent=2) + "\n", encoding="utf-8")
    return design


def confirmation_cohort_size(
    *,
    half_width: float,
    confidence: float = 0.95,
    assumed_rate: float = 0.5,
) -> int:
    """Planning-size a blinded confirmation cohort (normal approximation).

    This is *design-time power/precision planning* for Macro-F1 / recall
    confidence intervals — deliberately conservative and separate from the
    zero-failure acceptance-gate mathematics above. ``assumed_rate=0.5``
    maximises variance and is the honest default when the true rate is
    unknown.
    """

    _validate_confidence(confidence)
    if isinstance(half_width, bool) or not 0.0 < half_width < 1.0:
        raise ValueError("half_width must be strictly between 0 and 1")
    if isinstance(assumed_rate, bool) or not 0.0 < assumed_rate < 1.0:
        raise ValueError("assumed_rate must be strictly between 0 and 1")
    from statistics import NormalDist

    z = NormalDist().inv_cdf(1.0 - (1.0 - confidence) / 2.0)
    n = (z**2 * assumed_rate * (1.0 - assumed_rate)) / half_width**2
    return math.ceil(n)


def bind_design_to_inputs(design: dict[str, Any], *input_paths: str | Path) -> str:
    """Hash the frozen design together with its exact input artifacts."""

    payload = {
        "design_sha256": _design_hash(design),
        "inputs": {str(path): sha256_file(path) for path in input_paths},
    }
    import hashlib

    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _design_hash(design: dict[str, Any]) -> str:
    import hashlib

    return hashlib.sha256(
        json.dumps(design, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
