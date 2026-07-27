"""Label-free metamorphic checks for parsed-log features and safety decisions."""

from copy import deepcopy

import pytest

from src.contracts import ParsedLog
from src.diagnosis.decision_policy import evaluate_decision
from src.features.pipeline import FeaturePipeline


def _vibe_log(*, shift_us: int = 0, rows: int = 12) -> ParsedLog:
    samples = []
    for index in range(rows):
        samples.append(
            {
                "TimeUS": shift_us + index * 100_000,
                "VibeX": 1.0,
                "VibeY": 2.0,
                "VibeZ": 10.0 if index < rows - 2 else 45.0,
                "Clip0": 0,
                "Clip1": 0,
                "Clip2": 0,
            }
        )
    return {
        "metadata": {
            "duration_sec": rows / 10.0,
            "total_messages": rows,
            "message_types": {"VIBE": rows},
        },
        "messages": {"VIBE": samples},
        "parameters": {},
        "errors": [],
        "events": [],
        "mode_changes": [],
        "status_messages": [],
    }


def test_timestamp_shift_preserves_relative_anomaly_order():
    pipeline = FeaturePipeline()
    baseline = pipeline.extract(_vibe_log())
    shifted = pipeline.extract(_vibe_log(shift_us=7_000_000))

    assert shifted["vibe_z_tanomaly"] - baseline["vibe_z_tanomaly"] == pytest.approx(
        7_000_000
    )
    assert shifted["_temporal_discord"]["status"] == baseline["_temporal_discord"]["status"]


def test_exact_duplicate_messages_do_not_change_aggregates():
    pipeline = FeaturePipeline()
    baseline_log = _vibe_log()
    duplicated_log = deepcopy(baseline_log)
    duplicated_log["messages"]["VIBE"].extend(
        [deepcopy(duplicated_log["messages"]["VIBE"][3])] * 5
    )

    baseline = pipeline.extract(baseline_log)
    duplicated = pipeline.extract(duplicated_log)
    for name in ("vibe_z_mean", "vibe_z_std", "vibe_z_max", "vibe_z_tanomaly"):
        assert duplicated[name] == pytest.approx(baseline[name])


def test_required_message_removal_fails_closed_at_decision_boundary():
    pipeline = FeaturePipeline()
    features = pipeline.extract(_vibe_log())
    quality = features["_metadata"]["quality_report"]
    decision = evaluate_decision([], quality_report=quality)

    assert decision["status"] in {"insufficient_data", "uncertain"}
    assert decision["requires_human_review"] is True


def test_truncated_before_onset_does_not_assert_root_cause():
    pipeline = FeaturePipeline()
    truncated = pipeline.extract(_vibe_log(rows=8))
    quality = truncated["_metadata"]["quality_report"]
    decision = evaluate_decision([], quality_report=quality)

    assert truncated["_metadata"]["extraction_success"] is True
    assert decision["status"] != "confirmed"


def test_post_impact_noise_does_not_replace_preimpact_cause():
    decision = evaluate_decision(
        [
            {"failure_type": "power_instability", "confidence": 0.95, "detection_method": "rule"},
            {"failure_type": "vibration_high", "confidence": 0.55, "detection_method": "rule"},
        ]
    )
    assert decision["top_guess"] == "power_instability"
    assert decision["status"] == "uncertain"
    assert decision["requires_human_review"] is True


@pytest.mark.parametrize("confidence", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_confidence_fails_closed(confidence):
    decision = evaluate_decision(
        [{"failure_type": "vibration_high", "confidence": confidence, "detection_method": "rule"}]
    )
    assert decision["status"] == "uncertain"
    assert decision["requires_human_review"] is True
    assert "nonfinite_confidence" in decision["abstention_reasons"]


def test_malformed_confidence_fails_closed_without_raising():
    decision = evaluate_decision(
        [
            {"failure_type": "vibration_high", "confidence": "unknown", "detection_method": "rule"},
            {"failure_type": "ekf_failure", "confidence": None, "detection_method": "rule"},
        ]
    )

    assert decision["status"] == "uncertain"
    assert decision["requires_human_review"] is True
    assert "nonfinite_confidence" in decision["abstention_reasons"]
