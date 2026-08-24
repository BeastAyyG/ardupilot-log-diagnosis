"""Simultaneous lineage-bootstrap bounds for conditional sim-real fidelity."""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy.stats import wasserstein_distance

from .fidelity_statistics import STRATIFIER_FIELDS, robust_scale


def _stratum_key(record: dict[str, str]) -> tuple[str, ...]:
    return tuple(record[field] for field in STRATIFIER_FIELDS)


def _median_normalized_distance(real: np.ndarray, synthetic: np.ndarray) -> float:
    return float(
        np.median(
            [
                wasserstein_distance(real[:, column], synthetic[:, column])
                / robust_scale(real[:, column])
                for column in range(real.shape[1])
            ]
        )
    )


def simultaneous_worst_stratum_bounds(
    real: np.ndarray,
    synthetic: np.ndarray,
    real_records: list[dict[str, str]],
    synthetic_records: list[dict[str, str]],
    *,
    draws: int = 1000,
    seed: int = 20260823,
) -> dict[str, Any]:
    strata: list[tuple[np.ndarray, np.ndarray]] = []
    synthetic_keys = sorted({_stratum_key(record) for record in synthetic_records})
    for key in synthetic_keys:
        synthetic_positions = np.asarray(
            [
                index
                for index, record in enumerate(synthetic_records)
                if _stratum_key(record) == key
            ],
            dtype=int,
        )
        real_positions = np.asarray(
            [
                index
                for index, record in enumerate(real_records)
                if tuple(record[field] for field in STRATIFIER_FIELDS[:-1]) == key[:-1]
            ],
            dtype=int,
        )
        if len(real_positions) >= 8 and len(synthetic_positions) >= 3:
            strata.append((real_positions, synthetic_positions))
    if not strata:
        return {
            "complete": False,
            "pass": False,
            "status": "blocked_no_stratum_with_8_real_and_3_synthetic_lineages",
            "draws": 0,
        }

    rng = np.random.default_rng(seed)
    sim_real_worst: list[float] = []
    real_real_worst: list[float] = []
    for _ in range(draws):
        sim_draw: list[float] = []
        reference_draw: list[float] = []
        for real_positions, synthetic_positions in strata:
            real_sample = rng.choice(real_positions, len(real_positions), replace=True)
            synthetic_sample = rng.choice(
                synthetic_positions, len(synthetic_positions), replace=True
            )
            sim_draw.append(
                _median_normalized_distance(
                    real[real_sample], synthetic[synthetic_sample]
                )
            )
            order = rng.permutation(real_positions)
            half = len(order) // 2
            reference_draw.append(
                _median_normalized_distance(
                    real[order[:half]], real[order[half : 2 * half]]
                )
            )
        sim_real_worst.append(max(sim_draw))
        real_real_worst.append(max(reference_draw))
    sim_upper = float(np.quantile(sim_real_worst, 0.95))
    reference_upper = float(np.quantile(real_real_worst, 0.95))
    return {
        "complete": True,
        "pass": bool(sim_upper <= reference_upper),
        "status": "measured",
        "eligible_strata": len(strata),
        "draws": int(draws),
        "confidence_level": 0.95,
        "sim_real_worst_stratum_upper_95": sim_upper,
        "real_real_worst_stratum_reference_upper_95": reference_upper,
        "resampling_unit": "lineage_root_id",
        "simultaneous_family_statistic": "maximum_stratum_median_normalized_wasserstein",
        "seed": seed,
    }
