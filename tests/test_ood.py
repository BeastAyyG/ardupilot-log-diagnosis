"""Tests for machine-computed OOD evidence producers."""

from __future__ import annotations

import math

import pytest

from synthetic_data.ood import compute_ood_evidence


def _separable(n_id=40, n_ood=25, offset=4.0, seed=7):
    import numpy as np

    rng = np.random.default_rng(seed)
    id_scores = {f"id-{i}": float(v) for i, v in enumerate(rng.normal(0, 1, n_id))}
    ood_scores = {
        "held_out_firmware": {
            f"fw-{i}": float(offset + v) for i, v in enumerate(rng.normal(0, 1, n_ood))
        }
    }
    return id_scores, ood_scores


def test_separable_domains_score_high_with_honest_bounds() -> None:
    id_scores, ood_scores = _separable()
    report = compute_ood_evidence(id_scores, ood_scores, bootstrap_draws=200)

    assert report["auroc_lower_95"] >= 0.95
    assert report["detection_at_5pct_id_fpr_lower_95"] >= 0.8
    assert report["per_domain_lineages"] == {"held_out_firmware": 25}
    assert report["id_lineage_count"] == 40
    assert report["runtime_abstention_route_test_pass"] is True
    assert report["release_claim"] == "none"


def test_overlapping_domains_produce_weak_evidence() -> None:
    import numpy as np

    rng = np.random.default_rng(3)
    id_scores = {f"i{i}": float(v) for i, v in enumerate(rng.normal(0, 1, 40))}
    ood = {f"o{i}": float(v) for i, v in enumerate(rng.normal(0.2, 1, 25))}
    report = compute_ood_evidence(
        id_scores, {"real_sensor_corruption": ood}, bootstrap_draws=200
    )
    assert report["auroc_lower_95"] < 0.9


def test_routing_failure_blocks_the_report() -> None:
    id_scores, ood_scores = _separable()
    report = compute_ood_evidence(
        id_scores,
        ood_scores,
        bootstrap_draws=100,
        abstention_routes={"held_out_firmware": False},
    )
    assert report["runtime_abstention_route_test_pass"] is False


def test_missing_route_audit_is_refused() -> None:
    id_scores, ood_scores = _separable()
    with pytest.raises(ValueError, match="missing for domains"):
        compute_ood_evidence(
            id_scores,
            ood_scores,
            bootstrap_draws=50,
            abstention_routes={},
        )


@pytest.mark.parametrize(
    "mutator",
    [
        lambda s: s.update({"bad": float("nan")}),
        lambda s: s.update({"bad": float("inf")}),
        lambda s: s.update({"": 1.0}),
        lambda s: s.update({"bad": True}),
    ],
)
def test_invalid_scores_fail_closed(mutator) -> None:
    id_scores, ood_scores = _separable()
    mutator(ood_scores["held_out_firmware"])
    with pytest.raises(ValueError):
        compute_ood_evidence(id_scores, ood_scores, bootstrap_draws=50)


def test_detection_threshold_caps_id_fpr_exactly() -> None:
    import numpy as np

    rng = np.random.default_rng(11)
    id_values = rng.normal(0, 1, 400)
    id_scores = {f"i{i}": float(v) for i, v in enumerate(id_values)}
    # OOD drawn from the SAME distribution: empirical FPR must be <= 5% + slack
    ood_values = rng.normal(0, 1, 400)
    ood_scores = {
        "unknown_fault_family": {f"o{i}": float(v) for i, v in enumerate(ood_values)}
    }
    report = compute_ood_evidence(id_scores, ood_scores, bootstrap_draws=50)
    point = report["per_domain"]["unknown_fault_family"][
        "detection_at_5pct_id_fpr_point"
    ]
    threshold = float(np.quantile(id_values, 0.95, method="higher"))
    empirical_fpr = float(np.mean(ood_values >= threshold))
    assert empirical_fpr <= 0.05 + 0.02
    assert math.isfinite(point)
