"""Lineage-level statistical tests for sim-real feature fidelity."""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy.spatial.distance import pdist, squareform
from scipy.stats import wasserstein_distance
from sklearn.base import clone
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from src.constants import FEATURE_NAMES

STRATIFIER_FIELDS = (
    "primary_label",
    "flight_phase",
    "vehicle_frame",
    "firmware_commit",
    "simulation_family",
)


def collapse_lineage_units(
    matrix: np.ndarray, records: list[dict[str, str]]
) -> np.ndarray:
    """Collapse correlated label arms to one global vector per lineage root."""

    if len(matrix) != len(records):
        raise ValueError("fidelity matrix and lineage records have different lengths")
    roots = [record.get("lineage_root_id", "").strip() for record in records]
    if any(not root for root in roots):
        raise ValueError("fidelity records require nonblank lineage_root_id")
    root_array = np.asarray(roots)
    return np.asarray(
        [np.median(matrix[root_array == root], axis=0) for root in sorted(set(roots))],
        dtype=float,
    )


def robust_scale(values: np.ndarray) -> float:
    q25, q75 = np.quantile(values, [0.25, 0.75])
    return max(float(q75 - q25), float(np.std(values)), 1e-9)


def feature_distances(real: np.ndarray, synthetic: np.ndarray) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for column, name in enumerate(FEATURE_NAMES):
        real_values = real[:, column]
        synthetic_values = synthetic[:, column]
        output.append(
            {
                "feature": name,
                "normalized_wasserstein": float(
                    wasserstein_distance(real_values, synthetic_values)
                    / robust_scale(real_values)
                ),
                "zero_prevalence_gap": abs(
                    float(np.mean(real_values == 0.0))
                    - float(np.mean(synthetic_values == 0.0))
                ),
                "real_median": float(np.median(real_values)),
                "synthetic_median": float(np.median(synthetic_values)),
            }
        )
    output.sort(key=lambda item: item["normalized_wasserstein"], reverse=True)
    return output


def real_real_envelope(
    real: np.ndarray,
    *,
    draws: int = 200,
    seed: int = 20260823,
) -> np.ndarray | None:
    if len(real) < 8:
        return None
    rng = np.random.default_rng(seed)
    distances = np.zeros((draws, real.shape[1]), dtype=float)
    size = len(real) // 2
    for draw in range(draws):
        order = rng.permutation(len(real))
        left = real[order[:size]]
        right = real[order[size : size * 2]]
        for column in range(real.shape[1]):
            distances[draw, column] = wasserstein_distance(
                left[:, column], right[:, column]
            ) / robust_scale(left[:, column])
    return np.quantile(distances, 0.95, axis=0)


def _cross_fitted_scores(
    estimator: Any,
    matrix: np.ndarray,
    domain: np.ndarray,
    folds: int,
) -> np.ndarray:
    scores = np.zeros(len(domain), dtype=float)
    splitter = StratifiedKFold(n_splits=folds, shuffle=True, random_state=42)
    for train, test in splitter.split(matrix, domain):
        fitted = clone(estimator).fit(matrix[train], domain[train])
        scores[test] = fitted.predict_proba(matrix[test])[:, 1]
    return scores


def _distinguishability(domain: np.ndarray, scores: np.ndarray) -> tuple[float, float]:
    raw = float(roc_auc_score(domain, scores))
    return raw, 0.5 + abs(raw - 0.5)


def source_classifier_tests(
    real: np.ndarray,
    synthetic: np.ndarray,
    *,
    permutation_draws: int = 1000,
    seed: int = 20260823,
) -> dict[str, Any]:
    """Run linear/nonlinear C2ST and a cross-fitted score permutation test."""

    combined = np.vstack((real, synthetic))
    domain = np.concatenate(
        (np.zeros(len(real), dtype=int), np.ones(len(synthetic), dtype=int))
    )
    folds = min(5, len(real), len(synthetic))
    if folds < 3:
        return {
            "complete": False,
            "status": "blocked_fewer_than_three_lineages_per_domain",
            "permutation_draws": 0,
        }
    estimators = {
        "linear_logistic": make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=1000, class_weight="balanced"),
        ),
        "nonlinear_random_forest": RandomForestClassifier(
            n_estimators=200,
            max_depth=4,
            min_samples_leaf=2,
            class_weight="balanced",
            n_jobs=1,
            random_state=42,
        ),
    }
    results: dict[str, dict[str, Any]] = {}
    score_vectors: list[np.ndarray] = []
    observed_family_statistic = 0.5
    try:
        for name, estimator in estimators.items():
            scores = _cross_fitted_scores(estimator, combined, domain, folds)
            raw, distinguishability = _distinguishability(domain, scores)
            results[name] = {
                "raw_auc": raw,
                "distinguishability_auc": distinguishability,
            }
            score_vectors.append(scores)
            observed_family_statistic = max(
                observed_family_statistic, distinguishability
            )
    except ValueError:
        return {
            "complete": False,
            "status": "blocked_stratified_cv_infeasible",
            "permutation_draws": 0,
        }

    rng = np.random.default_rng(seed)
    exceedances = 0
    for _ in range(permutation_draws):
        permuted = rng.permutation(domain)
        statistic = max(
            _distinguishability(permuted, scores)[1] for scores in score_vectors
        )
        exceedances += statistic >= observed_family_statistic
    return {
        "complete": True,
        "status": "measured",
        "folds": folds,
        "cv": "stratified_kfold_on_independent_lineage_units",
        "classifiers": results,
        "family_max_distinguishability_auc": observed_family_statistic,
        "permutation_draws": int(permutation_draws),
        "permutation_p_value": float((exceedances + 1) / (permutation_draws + 1)),
        "permutation_protocol": (
            "family-max label permutation against cross-fitted held-out scores"
        ),
        "permutation_seed": seed,
    }


def _standardize_combined(real: np.ndarray, synthetic: np.ndarray) -> np.ndarray:
    combined = np.vstack((real, synthetic)).astype(float)
    median = np.median(combined, axis=0)
    q25, q75 = np.quantile(combined, [0.25, 0.75], axis=0)
    scale = q75 - q25
    scale[scale <= 1e-12] = np.std(combined[:, scale <= 1e-12], axis=0)
    scale[scale <= 1e-12] = 1.0
    return (combined - median) / scale


def _mmd_from_kernel(kernel: np.ndarray, left: np.ndarray, right: np.ndarray) -> float:
    left_kernel = kernel[np.ix_(left, left)]
    right_kernel = kernel[np.ix_(right, right)]
    cross_kernel = kernel[np.ix_(left, right)]
    left_term = (left_kernel.sum() - np.trace(left_kernel)) / (
        len(left) * (len(left) - 1)
    )
    right_term = (right_kernel.sum() - np.trace(right_kernel)) / (
        len(right) * (len(right) - 1)
    )
    return float(left_term + right_term - 2.0 * cross_kernel.mean())


def mmd_test(
    real: np.ndarray,
    synthetic: np.ndarray,
    *,
    permutation_draws: int = 1000,
    seed: int = 20260823,
) -> dict[str, Any]:
    if len(real) < 2 or len(synthetic) < 2:
        return {"complete": False, "status": "blocked_fewer_than_two_units"}
    standardized = _standardize_combined(real, synthetic)
    squared = squareform(pdist(standardized, metric="sqeuclidean"))
    positive = squared[squared > 0]
    if not len(positive):
        return {"complete": False, "status": "blocked_zero_pairwise_distance"}
    bandwidth_squared = float(np.median(positive))
    kernel = np.exp(-squared / (2.0 * bandwidth_squared))
    real_positions = np.arange(len(real))
    synthetic_positions = np.arange(len(real), len(real) + len(synthetic))
    observed = _mmd_from_kernel(kernel, real_positions, synthetic_positions)
    rng = np.random.default_rng(seed)
    exceedances = 0
    all_positions = np.arange(len(standardized))
    for _ in range(permutation_draws):
        order = rng.permutation(all_positions)
        statistic = _mmd_from_kernel(
            kernel,
            order[: len(real)],
            order[len(real) :],
        )
        exceedances += statistic >= observed
    return {
        "complete": True,
        "status": "measured",
        "unbiased_mmd2": observed,
        "kernel": "rbf_on_robustly_standardized_features",
        "bandwidth": "median_nonzero_pairwise_squared_distance",
        "bandwidth_squared": bandwidth_squared,
        "permutation_draws": int(permutation_draws),
        "permutation_p_value": float((exceedances + 1) / (permutation_draws + 1)),
        "permutation_seed": seed,
    }


def conditional_feature_test_family(
    real: np.ndarray,
    synthetic: np.ndarray,
    real_records: list[dict[str, str]],
    synthetic_records: list[dict[str, str]],
    *,
    permutation_draws: int = 1000,
    seed: int = 20260823,
) -> dict[str, Any]:
    """Run C2ST and MMD within comparable label/operating strata."""

    results: list[dict[str, Any]] = []
    synthetic_keys = sorted({_stratum_key(record) for record in synthetic_records})
    for stratum_index, key in enumerate(synthetic_keys):
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
        if len(real_positions) < 3 or len(synthetic_positions) < 3:
            continue
        stratum_seed = seed + stratum_index * 1009
        classifier = source_classifier_tests(
            real[real_positions],
            synthetic[synthetic_positions],
            permutation_draws=permutation_draws,
            seed=stratum_seed,
        )
        mmd = mmd_test(
            real[real_positions],
            synthetic[synthetic_positions],
            permutation_draws=permutation_draws,
            seed=stratum_seed,
        )
        results.append(
            {
                "stratum": {name: value for name, value in zip(STRATIFIER_FIELDS, key)},
                "real_lineages": int(len(real_positions)),
                "synthetic_lineages": int(len(synthetic_positions)),
                "source_classifier": classifier,
                "mmd": mmd,
            }
        )
    if not results:
        return {
            "complete": False,
            "status": "blocked_no_comparable_stratum_with_three_units_per_domain",
            "strata": [],
            "permutation_draws": 0,
        }
    complete = all(
        row["source_classifier"].get("complete") is True
        and row["mmd"].get("complete") is True
        for row in results
    )
    family_count = len(results)
    p_values = [
        float(row["source_classifier"]["permutation_p_value"])
        for row in results
        if row["source_classifier"].get("complete") is True
    ]
    distinguishability = [
        float(row["source_classifier"]["family_max_distinguishability_auc"])
        for row in results
        if row["source_classifier"].get("complete") is True
    ]
    worst_index = int(np.argmax(distinguishability)) if distinguishability else 0
    worst_classifier = results[worst_index]["source_classifier"]
    return {
        "complete": complete,
        "status": "measured" if complete else "blocked_incomplete_test_family",
        "strata": results,
        "tested_strata": family_count,
        "permutation_draws": int(permutation_draws),
        "family_max_distinguishability_auc": (
            max(distinguishability) if distinguishability else None
        ),
        "familywise_source_classifier_permutation_p_value": (
            min(1.0, min(p_values) * family_count) if p_values else None
        ),
        "multiplicity_correction": "bonferroni_across_conditional_strata",
        "worst_linear_raw_auc": worst_classifier.get("classifiers", {})
        .get("linear_logistic", {})
        .get("raw_auc"),
        "nonlinear_c2st_complete": all(
            "nonlinear_random_forest" in row["source_classifier"].get("classifiers", {})
            for row in results
        ),
        "mmd_complete": all(row["mmd"].get("complete") is True for row in results),
        "resampling_unit": "lineage_root_id_within_stratum",
    }


def conditional_real_real_envelopes(
    real: np.ndarray,
    synthetic: np.ndarray,
    real_records: list[dict[str, str]],
    synthetic_records: list[dict[str, str]],
    *,
    draws: int = 200,
    seed: int = 20260823,
) -> dict[str, Any]:
    """Compare each sim-real stratum with its balanced real-real envelope."""

    results: list[dict[str, Any]] = []
    synthetic_keys = sorted({_stratum_key(record) for record in synthetic_records})
    for stratum_index, key in enumerate(synthetic_keys):
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
        if len(real_positions) < 8 or len(synthetic_positions) < 3:
            continue
        real_values = real[real_positions]
        synthetic_values = synthetic[synthetic_positions]
        envelope = real_real_envelope(
            real_values,
            draws=draws,
            seed=seed + stratum_index * 1009,
        )
        if envelope is None:
            continue
        observed_by_name = {
            row["feature"]: row["normalized_wasserstein"]
            for row in feature_distances(real_values, synthetic_values)
        }
        observed = np.asarray([observed_by_name[name] for name in FEATURE_NAMES])
        results.append(
            {
                "stratum": {name: value for name, value in zip(STRATIFIER_FIELDS, key)},
                "real_lineages": int(len(real_positions)),
                "synthetic_lineages": int(len(synthetic_positions)),
                "features_outside_real_real_95_envelope": float(
                    np.mean(observed > envelope)
                ),
            }
        )
    return {
        "complete": bool(results),
        "status": "measured" if results else "blocked_insufficient_stratum_support",
        "draws": int(draws) if results else 0,
        "strata": results,
        "maximum_features_outside_real_real_95_envelope": (
            max(row["features_outside_real_real_95_envelope"] for row in results)
            if results
            else None
        ),
        "resampling_unit": "lineage_root_id_within_stratum",
    }


def _stratum_key(record: dict[str, str]) -> tuple[str, ...]:
    return tuple(record[field] for field in STRATIFIER_FIELDS)
