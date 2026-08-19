from pathlib import Path
import zipfile

from src.analysis.event_correlation import build_event_timeline
from src.analysis.telemetry_quality import availability_matrix, timestamp_health
from src.diagnosis.decision_policy import evaluate_decision
from src.diagnosis.hybrid_engine import HybridEngine
from src.diagnosis.log_quality import LogQualityEngine
from src.diagnosis.rule_engine import RuleEngine
from src.reporting.parameter_validation import validate_parameters
from src.reporting.privacy import export_expert_bundle, scrub_report


def _parsed():
    return {
        "metadata": {"duration_sec": 2.0, "message_types": {"ATT": 4, "GPS": 2, "ERR": 1}},
        "messages": {"ATT": [{"TimeUS": 0}, {"TimeUS": 500_000}, {"TimeUS": 1_000_000}, {"TimeUS": 1_500_000}]},
        "errors": [{"time_us": 1_000_000, "subsystem_name": "GPS"}],
        "events": [],
        "mode_changes": [{"time_us": 1_100_000, "mode_name": "RTL"}],
        "status_messages": [],
        "parameter_changes": [],
        "parameters": {},
    }


def test_timestamp_and_availability_are_explicit():
    health = timestamp_health(_parsed())
    assert health["status"] == "reliable"
    matrix = availability_matrix(_parsed())
    assert matrix["streams"]["ATT"]["rate_hz"] == 2.0
    assert matrix["capabilities"]["gps_metrics"]["status"] == "reliable"


def test_availability_gates_ardupilot_only_capabilities_by_input_format():
    parsed = _parsed()
    parsed["metadata"]["file_format"] = {"format": "px4_ulog", "supported": True}
    matrix = availability_matrix(parsed)
    assert matrix["capabilities"]["diagnosis"]["status"] == "unsupported"
    assert matrix["capabilities"]["health_score"]["status"] == "reliable"


def test_generic_format_does_not_run_ardupilot_root_cause_rules():
    features = {
        "vibe_z_max": 80.0,
        "_metadata": {
            "quality_report": {
                "overall_status": "RELIABLE",
                "input_format": {"format": "px4_ulog"},
            }
        },
    }
    assert RuleEngine().diagnose(features) == []
    engine = HybridEngine()
    assert engine.diagnose(features) == []
    assert engine.last_explain_data["format_gate"]["status"] == "unsupported"
    decision = evaluate_decision([], quality_report=features["_metadata"]["quality_report"])
    assert decision["status"] == "uncertain"
    assert decision["requires_human_review"] is True


def test_generic_format_quality_report_does_not_recommend_ardupilot_logging_flags():
    parsed = _parsed()
    parsed["metadata"]["file_format"] = {"format": "px4_ulog", "supported": True}
    parsed["metadata"]["total_messages"] = 20
    quality = LogQualityEngine().evaluate(parsed)
    assert quality["overall_status"] == "RELIABLE"
    assert quality["capabilities"]["vibration_analysis"]["status"] == "UNSUPPORTED"
    assert quality["capabilities"]["compass_gps_navigation"]["status"] == "UNSUPPORTED"
    assert all("LOG_BITMASK" not in str(item) for item in quality["actionable_recommendations"])


def test_event_timeline_correlates_nearby_response():
    timeline = build_event_timeline(_parsed())
    assert timeline["events"]
    assert timeline["causal_graph"]["edges"][0]["to"] == "RTL"


def test_parameter_validation_never_authorizes_writes():
    result = validate_parameters({"BATT_LOW_VOLT": -1, "INS_GYRO_FILTER": 40, "CUSTOM": 1})
    assert result["status"] == "invalid"
    assert result["invalid_count"] == 1
    assert result["write_parameters"] is False


def test_privacy_scrubber_and_bundle(tmp_path: Path):
    report = {"metadata": {"location": {"lat": 1}}, "features": {"latitude": 2}, "hardware_report": {"raw_message_explorer": {"streams": {"GPS": {"samples": [{"Lat": 1, "Lng": 2}]}}}, "parameters": {"lines": ["SERIAL1 10", "ATC_RAT_RLL_P 0.1"]}}}
    scrubbed = scrub_report(report)
    assert "location" not in scrubbed["metadata"]
    assert scrubbed["hardware_report"]["parameters"]["lines"] == ["ATC_RAT_RLL_P 0.1"]
    assert "Lat" not in scrubbed["hardware_report"]["raw_message_explorer"]["streams"]["GPS"]["samples"][0]
    source_log = tmp_path / "source.bin"
    source_log.write_bytes(b"raw")
    output = export_expert_bundle(report, tmp_path / "bundle.zip", log_path=source_log)
    assert output.exists()
    with zipfile.ZipFile(output) as archive:
        assert all(not name.startswith("input/") for name in archive.namelist())
