"""Tests for domain randomization and advisory active learning."""

from __future__ import annotations

import pytest

from synthetic_data.active_learning import propose_next_batch
from synthetic_data.randomization import (
    bands_digest,
    sample_pair_environment,
    validate_bands,
)


class TestRandomization:
    def test_pair_arms_share_one_latent_environment(self) -> None:
        control = sample_pair_environment(pair_seed=42)
        intervention = sample_pair_environment(pair_seed=42)
        assert control == intervention
        other = sample_pair_environment(pair_seed=43)
        assert other["environment"] != control["environment"]

    def test_samples_stay_inside_preregistered_bands(self) -> None:
        bands = {"sim_wind_spd_mps": (2.0, 5.0)}
        digest = bands_digest(bands)
        for seed in range(25):
            sample = sample_pair_environment(pair_seed=seed, bands=bands)
            value = sample["environment"]["sim_wind_spd_mps"]
            assert 2.0 <= value <= 5.0
            assert sample["bands_sha256"] == digest

    @pytest.mark.parametrize(
        "bad",
        [{}, {"x": (1.0, 0.0)}, {"x": (float("nan"), 1.0)}, {"": (0, 1)}],
    )
    def test_invalid_bands_fail_closed(self, bad) -> None:
        with pytest.raises(ValueError):
            validate_bands(bad)

    def test_band_change_is_detectable_via_digest(self) -> None:
        before = sample_pair_environment(pair_seed=7)
        widened = dict(before)
        after = sample_pair_environment(
            pair_seed=7, bands={"sim_wind_spd_mps": (0.0, 12.0)}
        )
        assert before["bands_sha256"] != after["bands_sha256"]
        assert "environment" in after and "environment" in widened


class TestActiveLearning:
    def test_unsupported_classes_rank_first(self) -> None:
        proposal = propose_next_batch(
            per_class={
                "healthy": {"recall_lower": 0.99, "ece": 0.01, "lineages": 50},
                "rc_failsafe": {"recall_lower": 0.6, "ece": 0.02, "lineages": 3},
                "power_instability": {
                    "recall_lower": 0.95,
                    "ece": 0.09,
                    "lineages": 40,
                },
            },
            minimum_lineages=25,
            scenario_for_class={"rc_failsafe": "rc_failsafe"},
            capacity=3,
        )
        order = [item["class"] for item in proposal["proposals"]]
        assert order[0] == "rc_failsafe"
        assert (
            "lineage support below preregistered minimum"
            in (proposal["proposals"][0]["priority_reasons"])
        )
        assert proposal["advisory"] is True
        assert proposal["promotes_nothing"] is True

    def test_capacity_and_validation(self) -> None:
        stats = {f"c{i}": {"recall_lower": 0.8} for i in range(5)}
        out = propose_next_batch(per_class=stats, minimum_lineages=10, capacity=2)
        assert len(out["proposals"]) == 2
        with pytest.raises(ValueError):
            propose_next_batch(per_class={}, minimum_lineages=10)
        with pytest.raises(ValueError):
            propose_next_batch(per_class={"a": {"bogus": 1}}, minimum_lineages=10)
