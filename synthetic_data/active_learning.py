"""Advisory active-learning proposals; never promotes or rewrites gates."""

from __future__ import annotations

from typing import Any

PROPOSAL_SCHEMA = "logdiagnosis.active-learning-proposal/v1"


def propose_next_batch(
    *,
    per_class: dict[str, dict[str, float]],
    minimum_lineages: int,
    scenario_for_class: dict[str, str] | None = None,
    capacity: int = 10,
) -> dict[str, Any]:
    """Rank classes by evidence deficit; purely advisory output.

    ``per_class`` maps class -> optional keys: ``recall_lower`` (lower
    confidence bound), ``ece`` (calibration error), ``lineages`` (support).
    Deficits are ordered: unsupported classes first, then weakest recall
    bound, then worst calibration error.
    """

    if isinstance(capacity, bool) or capacity < 1:
        raise ValueError("capacity must be a positive integer")
    if not per_class:
        raise ValueError("proposal requires per-class statistics")
    for name, stats in per_class.items():
        if not name:
            raise ValueError("class names must be non-empty")
        for key, value in stats.items():
            if key not in {"recall_lower", "ece", "lineages"}:
                raise ValueError(f"unknown per-class stat: {key}")
            if isinstance(value, bool) or value < 0:
                raise ValueError(f"{name}.{key} must be non-negative")

    def deficit(name: str) -> tuple[int, float, float]:
        stats = per_class[name]
        support_gap = 1 if float(stats.get("lineages", 0)) < minimum_lineages else 0
        recall = float(stats.get("recall_lower", 1.0))
        ece = float(stats.get("ece", 0.0))
        return (support_gap, round(1.0 - recall, 6), round(ece, 6))

    ranked = sorted(per_class, key=deficit, reverse=True)
    proposals = []
    for name in ranked[:capacity]:
        stats = per_class[name]
        support_gap = float(stats.get("lineages", 0)) < minimum_lineages
        reasons = []
        if support_gap:
            reasons.append("lineage support below preregistered minimum")
        if float(stats.get("recall_lower", 1.0)) < 0.9:
            reasons.append("recall lower bound below 0.9")
        if float(stats.get("ece", 0.0)) > 0.05:
            reasons.append("calibration error above 0.05")
        proposals.append(
            {
                "class": name,
                "scenario": (scenario_for_class or {}).get(name, name),
                "priority_reasons": reasons
                or ["lowest residual deficit; routine top-up"],
                "suggested_units_hint": minimum_lineages * (2 if support_gap else 1),
            }
        )
    return {
        "schema": PROPOSAL_SCHEMA,
        "advisory": True,
        "promotes_nothing": True,
        "minimum_lineages": int(minimum_lineages),
        "proposals": proposals,
    }
