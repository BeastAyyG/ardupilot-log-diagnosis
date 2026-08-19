from pathlib import Path
import importlib.util

import pytest

from src.parser.file_format import detect_file_format, supported_format_kinds
from src.reporting.parameter_diff import diff_parameters, load_parameter_file
from src.reporting.hardware import HardwareReportBuilder


def test_detect_file_format_and_hash(tmp_path: Path):
    path = tmp_path / "flight.BIN"
    path.write_bytes(b"\xa3\x95payload")
    result = detect_file_format(path, hash_file=True)
    assert result["format"] == "ardupilot_bin"
    assert result["supported"] is True
    assert len(result["sha256"]) == 64
    assert "ardupilot_bin" in supported_format_kinds()


def test_detect_ulog_uses_generic_adapter_when_available(tmp_path: Path):
    path = tmp_path / "flight.ulg"
    path.write_bytes(b"ULog" + b"\x00" * 10)
    result = detect_file_format(path)
    assert result["format"] == "px4_ulog"
    assert result["supported"] is True
    assert result["parser"] == "pyulog.ULog"
    assert result["capabilities"] == ["generic_telemetry_checks"]


def test_detect_text_log_uses_pymavlink_text_adapter(tmp_path: Path):
    path = tmp_path / "flight.log"
    path.write_text("", encoding="utf-8")
    result = detect_file_format(path)
    assert result["format"] == "text_log"
    assert result["supported"] is True
    assert result["parser"] == "pymavlink.DFReader_text"


def test_detect_betaflight_blackbox_uses_optional_adapter(tmp_path: Path):
    path = tmp_path / "flight.bbl"
    path.write_bytes(b"H Product:Blackbox flight data recorder\n")
    result = detect_file_format(path)
    assert result["format"] == "betaflight_bbl"
    assert result["parser"] == "orangebox.Parser"
    assert result["supported"] is (importlib.util.find_spec("orangebox") is not None)
    assert result["adapter_dependency"] == "orangebox"
    assert result["adapter_available"] is result["supported"]


def test_empty_text_log_returns_quality_report_without_leaking_file_handle(tmp_path: Path):
    from src.parser.bin_parser import LogParser

    path = tmp_path / "empty.log"
    path.write_text("", encoding="utf-8")
    parsed = LogParser(str(path)).parse()
    assert parsed["metadata"]["quality_report"]["overall_status"] == "UNSUPPORTED"
    assert parsed["metadata"]["parse_error"]


def test_parameter_file_and_semantic_diff(tmp_path: Path):
    before = tmp_path / "before.param"
    after = tmp_path / "after.param"
    before.write_text("# comment\nATC_RAT_RLL_P,0.1\nCOMPASS_OFS_X,2\n", encoding="utf-8")
    after.write_text("ATC_RAT_RLL_P,0.10000001\nCOMPASS_OFS_X,4\nNEW_PARAM 3\n", encoding="utf-8")
    left = load_parameter_file(before)
    right = load_parameter_file(after)
    report = diff_parameters(left, right)
    assert report["changed_count"] == 1
    assert report["added_count"] == 1
    assert any(item["parameter"] == "COMPASS_OFS_X" and item["risk"] == "high" for item in report["changes"])


def test_parameter_file_rejects_malformed_rows(tmp_path: Path):
    path = tmp_path / "bad.param"
    path.write_text("NOT_A_PAIR\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid parameter row"):
        load_parameter_file(path)


def test_hardware_report_contains_sensor_and_health_cards(tmp_path: Path):
    path = tmp_path / "flight.bin"
    path.write_bytes(b"payload")
    parsed = {
        "metadata": {
            "filepath": str(path),
            "vehicle_type": "Copter",
            "firmware_version": "4.5.1",
            "duration_sec": 10.0,
            "total_messages": 4,
            "message_types": {"MSG": 1, "PARM": 1, "VIBE": 2, "PM": 1},
            "quality_report": {"overall_status": "DEGRADED"},
        },
        "messages": {"PM": [{"Load": 40, "Mem": 1000, "TimeUS": 1}]},
        "parameters": {"ATC_RAT_RLL_P": 0.1, "COMPASS_OFS_X": 2},
        "errors": [{"subsystem": 30, "subsystem_name": "INTERNAL_ERROR"}],
        "status_messages": [{"message": "ArduCopter 4.5.1"}],
        "events": [],
        "mode_changes": [],
    }
    report = HardwareReportBuilder().build(parsed)
    assert report["schema_version"] == "hardware-report.v1"
    assert report["sensors"]["imu"]["present"] is True
    assert report["system_health"]["watchdog_or_internal_error"] is True
    assert report["parameters"]["lines"] == ["ATC_RAT_RLL_P,0.1"]
    assert report["raw_message_explorer"]["schema_version"] == "raw-message-explorer.v1"
    assert report["failsafe_checks"] is report["safety_findings"]
    assert report["end_of_log_classifier"] is report["end_of_log"]


def test_hardware_report_contains_detailed_mission_plan_review(tmp_path: Path):
    path = tmp_path / "mission.bin"
    path.write_bytes(b"payload")
    parsed = {
        "metadata": {"filepath": str(path), "message_types": {"CMD": 1, "GPS": 1}, "total_messages": 2, "vehicle_type": "Copter", "firmware_version": "4.5", "duration_sec": 1.0, "quality_report": {}},
        "messages": {"CMD": [{"CNum": 0, "CId": 16, "Lat": 37.422, "Lng": -122.084, "Alt": 20}], "GPS": [{"Lat": 37.422, "Lng": -122.084, "Alt": 20, "TimeUS": 1}]},
        "parameters": {}, "parameter_changes": [], "errors": [], "events": [], "mode_changes": [], "status_messages": [],
    }
    report = HardwareReportBuilder().build(parsed)
    assert report["mission_plan_review"]["schema_version"] == "mission-plan.v1"
    assert report["mission_compliance_detail"]["hit_count"] == 1


def test_changed_parameter_export_uses_in_log_changes(tmp_path: Path):
    path = tmp_path / "flight.bin"
    path.write_bytes(b"payload")
    parsed = {
        "metadata": {"filepath": str(path), "message_types": {}, "total_messages": 0, "vehicle_type": "Copter", "firmware_version": "Unknown", "duration_sec": 0.0, "quality_report": {}},
        "messages": {}, "parameters": {"A": 1, "B": 2}, "parameter_changes": [{"name": "B", "old_value": 1, "new_value": 2}], "errors": [], "events": [], "mode_changes": [], "status_messages": [],
    }
    report = HardwareReportBuilder().build(parsed, parameter_mode="changed")
    assert report["parameters"]["lines"] == ["B,2"]


def test_parameter_change_audit_has_phase_and_risk_context():
    parsed = {
        "parameter_changes": [{"name": "ATC_RAT_RLL_P", "old_value": 0.1, "new_value": 0.2, "time_us": 2_000_000}],
        "mode_changes": [{"time_us": 1_000_000, "mode_name": "LOITER"}],
    }
    report = HardwareReportBuilder().build({"metadata": {"quality_report": {}}, "messages": {}, "parameters": {}, "parameter_changes": parsed["parameter_changes"], "mode_changes": parsed["mode_changes"], "errors": [], "events": [], "status_messages": []})
    assert report["parameter_change_audit"]["changes"][0]["mode"] == "LOITER"
    assert report["parameter_change_audit"]["changes"][0]["risk"] == "medium"
