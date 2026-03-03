"""Calibration and false-critical-rate utilities.

Provides:
- ECE (Expected Calibration Error) computation
- Abstention rate reporting
- False-Critical Rate (FCR) audit

These satisfy Hard Gate E and P4-03.
"""

from __future__ import annotations

from typing import List, Tuple


# ---------------------------------------------------------------------------
# ECE
# ---------------------------------------------------------------------------

def compute_ece(
    confidences: List[float],
    correct: List[bool],
    n_bins: int = 10,
) -> float:
    """Compute Expected Calibration Error (equal-width bins).

    Args:
        confidences: Predicted confidence values in [0, 1].
        correct: Whether the top-1 prediction was correct for each sample.
        n_bins: Number of equal-width bins.

    Returns:
        ECE as a float in [0, 1].  Lower is better; target <= 0.08.
    """
    if not confidences:
        return 0.0

    n = len(confidences)
    bins: List[List[Tuple[float, bool]]] = [[] for _ in range(n_bins)]

    for conf, corr in zip(confidences, correct):
        idx = min(int(conf * n_bins), n_bins - 1)
        bins[idx].append((conf, corr))

    ece = 0.0
    for bucket in bins:
        if not bucket:
            continue
        size = len(bucket)
        avg_conf = sum(c for c, _ in bucket) / size
        avg_acc = sum(1 for _, ok in bucket if ok) / size
        ece += (size / n) * abs(avg_acc - avg_conf)

    return float(ece)


# ---------------------------------------------------------------------------
# Abstention rate
# ---------------------------------------------------------------------------

def compute_abstention_rate(decisions: List[dict]) -> float:
    """Return fraction of decisions with status == 'uncertain' or requires_human_review."""
    if not decisions:
        return 0.0
    uncertain = sum(
        1 for d in decisions
        if d.get("status") == "uncertain" or d.get("requires_human_review")
    )
    return uncertain / len(decisions)


# ---------------------------------------------------------------------------
# False-Critical Rate (FCR)
# ---------------------------------------------------------------------------

def compute_false_critical_rate(results: List[dict]) -> float:
    """Compute FCR: fraction of healthy logs that receive a critical diagnosis.

    A result dict should have:
      - ``ground_truth``: list of true labels (e.g. ["healthy"])
      - ``predicted``: list of diagnosis dicts with ``severity`` field

    FCR = |healthy logs with ≥1 critical prediction| / |healthy logs|
    Target: FCR <= 0.10
    """
    healthy_total = 0
    false_criticals = 0

    for res in results:
        gt = res.get("ground_truth", [])
        preds = res.get("predicted", [])

        if "healthy" not in gt:
            continue

        healthy_total += 1
        if any(p.get("severity") == "critical" for p in preds):
            false_criticals += 1

    if healthy_total == 0:
        return 0.0
    return false_criticals / healthy_total


# ---------------------------------------------------------------------------
# Full calibration report
# ---------------------------------------------------------------------------

def generate_calibration_report(
    results: List[dict],
    decisions: List[dict] | None = None,
) -> dict:
    """Generate a structured calibration + FCR report.

    Args:
        results: List of result dicts (ground_truth, predicted).
        decisions: Optional list of ``evaluate_decision`` outputs.

    Returns:
        Dict with keys: ece, abstention_rate, false_critical_rate, n_samples,
        n_healthy, target_met.
    """
    # Collect (confidence, correct) pairs for ECE
    confidences: List[float] = []
    correct_flags: List[bool] = []

    for res in results:
        gt = set(res.get("ground_truth", []))
        preds = res.get("predicted", [])
        if preds:
            top = preds[0]
            conf = float(top.get("confidence", 0.0))
            is_correct = top.get("failure_type") in gt
            confidences.append(conf)
            correct_flags.append(is_correct)

    ece = compute_ece(confidences, correct_flags)
    fcr = compute_false_critical_rate(results)
    abstention = compute_abstention_rate(decisions or [])

    return {
        "n_samples": len(results),
        "n_healthy": sum(
            1 for r in results if "healthy" in r.get("ground_truth", [])
        ),
        "ece": round(ece, 4),
        "abstention_rate": round(abstention, 4),
        "false_critical_rate": round(fcr, 4),
        "target_met": {
            "ece_le_0.08": ece <= 0.08,
            "fcr_le_0.10": fcr <= 0.10,
        },
    }
