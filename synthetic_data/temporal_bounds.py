"""Familywise lineage bounds for raw temporal sim-real summaries."""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy.stats import wasserstein_distance

from .fidelity_statistics import STRATIFIER_FIELDS, robust_scale


def _key(stratum: dict[str, Any]) -> tuple[str, ...]:
    return tuple(str(stratum.get(name, "")) for name in STRATIFIER_FIELDS)


def evaluate_temporal_summaries(
    summaries: list[dict[str, Any]], design: dict[str, Any]
) -> dict[str, Any]:
    required = design["required_strata"]
    minimum = int(design["minimum_lineages_per_domain_per_stratum"])
    metric_names = sorted(summaries[0]["metrics"]) if summaries else []
    prepared: list[dict[str, Any]] = []
    missing: list[dict[str, str]] = []
    for entry in required:
        key = _key(entry)
        real_rows = [
            row
            for row in summaries
            if row["domain"] == "real" and _key(row["stratum"])[:-1] == key[:-1]
        ]
        synthetic_rows = [
            row
            for row in summaries
            if row["domain"] == "synthetic" and _key(row["stratum"]) == key
        ]
        if len(real_rows) < minimum or len(synthetic_rows) < minimum:
            missing.append({name: str(entry[name]) for name in STRATIFIER_FIELDS})
            continue
        real = np.asarray(
            [[row["metrics"][name] for name in metric_names] for row in real_rows],
            dtype=float,
        )
        synthetic = np.asarray(
            [[row["metrics"][name] for name in metric_names] for row in synthetic_rows],
            dtype=float,
        )
        scales = np.asarray(
            [robust_scale(real[:, index]) for index in range(len(metric_names))]
        )
        observed = np.asarray(
            [
                wasserstein_distance(real[:, index], synthetic[:, index])
                / scales[index]
                for index in range(len(metric_names))
            ]
        )
        prepared.append(
            {
                "key": key,
                "real": real,
                "synthetic": synthetic,
                "scales": scales,
                "observed": observed,
                "real_count": len(real_rows),
                "synthetic_count": len(synthetic_rows),
            }
        )
    if missing or not prepared or not metric_names:
        return {
            "complete": False,
            "raw_temporal_checks_pass": False,
            "required_strata": len(required),
            "evaluated_strata": len(prepared),
            "missing_strata": len(missing),
            "missing_strata_detail": missing,
            "metric_count": len(metric_names),
            "status": "blocked_missing_or_under_supported_temporal_strata",
        }

    draws = int(design["bootstrap_draws"])
    rng = np.random.default_rng(int(design["seed"]))
    sim_real_family: list[float] = []
    real_real_family: list[float] = []
    for _ in range(draws):
        sim_draw: list[float] = []
        reference_draw: list[float] = []
        for item in prepared:
            real = item["real"]
            synthetic = item["synthetic"]
            scales = item["scales"]
            sampled_real = real[rng.choice(len(real), size=len(real), replace=True)]
            sampled_synthetic = synthetic[
                rng.choice(len(synthetic), size=len(synthetic), replace=True)
            ]
            for index in range(len(metric_names)):
                sim_draw.append(
                    wasserstein_distance(
                        sampled_real[:, index], sampled_synthetic[:, index]
                    )
                    / scales[index]
                )
            left = real[rng.choice(len(real), size=len(real), replace=True)]
            right = real[rng.choice(len(real), size=len(synthetic), replace=True)]
            for index in range(len(metric_names)):
                reference_draw.append(
                    wasserstein_distance(left[:, index], right[:, index])
                    / scales[index]
                )
        sim_real_family.append(max(sim_draw))
        real_real_family.append(max(reference_draw))

    sim_upper = float(np.quantile(sim_real_family, 0.95))
    reference_upper = float(np.quantile(real_real_family, 0.95))
    strata: list[dict[str, Any]] = []
    for item in prepared:
        real = item["real"]
        synthetic = item["synthetic"]
        strata.append(
            {
                "stratum": {
                    name: value for name, value in zip(STRATIFIER_FIELDS, item["key"])
                },
                "real_lineages": item["real_count"],
                "synthetic_lineages": item["synthetic_count"],
                "metrics": {
                    name: {
                        "normalized_wasserstein": float(item["observed"][index]),
                        "real_median": float(np.median(real[:, index])),
                        "synthetic_median": float(np.median(synthetic[:, index])),
                    }
                    for index, name in enumerate(metric_names)
                },
            }
        )
    observed_family_max = max(float(np.max(item["observed"])) for item in prepared)
    passed = bool(observed_family_max <= reference_upper)
    return {
        "complete": True,
        "raw_temporal_checks_pass": passed,
        "status": "measured_pass" if passed else "measured_outside_real_real_envelope",
        "required_strata": len(required),
        "evaluated_strata": len(prepared),
        "missing_strata": 0,
        "missing_strata_detail": [],
        "metric_count": len(metric_names),
        "metric_names": metric_names,
        "strata": strata,
        "bootstrap_draws": draws,
        "confidence_level": 0.95,
        "sim_real_family_max_upper_95": sim_upper,
        "sim_real_observed_family_max": observed_family_max,
        "real_real_family_max_reference_upper_95": reference_upper,
        "family_statistic": "maximum normalized Wasserstein across strata and metrics",
        "resampling_unit": "lineage_root_id",
        "seed": int(design["seed"]),
    }
