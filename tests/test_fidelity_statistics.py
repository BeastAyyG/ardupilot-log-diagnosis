"""Independent-unit tests for the advanced feature-fidelity family."""

from __future__ import annotations

import numpy as np

from src.constants import FEATURE_NAMES
from synthetic_data.fidelity_bounds import simultaneous_worst_stratum_bounds
from synthetic_data.fidelity_statistics import (
    conditional_real_real_envelopes,
    mmd_test,
    source_classifier_tests,
)


def test_advanced_fidelity_statistics_use_independent_units() -> None:
    rng = np.random.default_rng(12)
    real = rng.normal(0, 1, size=(10, len(FEATURE_NAMES)))
    synthetic = real + rng.normal(0, 0.05, size=real.shape)
    classifiers = source_classifier_tests(
        real,
        synthetic,
        permutation_draws=49,
        seed=7,
    )
    mmd = mmd_test(real, synthetic, permutation_draws=49, seed=7)
    real_records = [
        {
            "primary_label": "thrust_loss",
            "flight_phase": "hover",
            "vehicle_frame": "quad",
            "firmware_commit": "Copter-4.6.2",
            "simulation_family": "physical",
        }
        for _ in range(len(real))
    ]
    synthetic_records = [
        {
            "primary_label": "thrust_loss",
            "flight_phase": "hover",
            "vehicle_frame": "quad",
            "firmware_commit": "Copter-4.6.2",
            "simulation_family": "thrust_loss",
        }
        for _ in range(len(synthetic))
    ]
    bounds = simultaneous_worst_stratum_bounds(
        real,
        synthetic,
        real_records,
        synthetic_records,
        draws=25,
        seed=7,
    )
    envelopes = conditional_real_real_envelopes(
        real,
        synthetic,
        real_records,
        synthetic_records,
        draws=25,
        seed=7,
    )

    assert classifiers["complete"] is True
    assert set(classifiers["classifiers"]) == {
        "linear_logistic",
        "nonlinear_random_forest",
    }
    assert classifiers["permutation_draws"] == 49
    assert mmd["complete"] is True
    assert mmd["permutation_draws"] == 49
    assert bounds["complete"] is True
    assert bounds["eligible_strata"] == 1
    assert bounds["resampling_unit"] == "lineage_root_id"
    assert envelopes["complete"] is True
    assert envelopes["strata"][0]["real_lineages"] == 10
    assert 0 <= envelopes["maximum_features_outside_real_real_95_envelope"] <= 1
