"""Tests for the Step 4 external baselines (training/baselines)."""

from training.baselines import loganalyzer_map, llm_baseline


def test_loganalyzer_maps_known_checks():
    report = {"loganalyzer": {"Vibe levels": "high", "GPS": "glitch"}}
    assert loganalyzer_map.predict_label(report) in {"vibration_high", "gps_quality_poor"}


def test_loganalyzer_abstains_on_neutral_verdict():
    report = {"loganalyzer": {"Vibe levels": "OK", "Compass": "pass"}}
    assert loganalyzer_map.predict_label(report) is None


def test_loganalyzer_abstains_without_input():
    assert loganalyzer_map.predict_label({}) is None
    assert loganalyzer_map.predict_label({"other": 1}) is None


def test_loganalyzer_coverage_is_partial_by_design():
    cov = loganalyzer_map.coverage()
    assert "setup_error" in cov["cannot_predict"]
    assert "vibration_high" in cov["can_predict"]


def test_llm_baseline_refuses_without_key(monkeypatch):
    monkeypatch.delenv("ARDUPILOT_LLM_API_KEY", raising=False)
    try:
        llm_baseline.predict_label({"diagnoses": []})
        assert False, "should have raised without a key"
    except RuntimeError as exc:
        assert "ARDUPILOT_LLM_API_KEY" in str(exc)
