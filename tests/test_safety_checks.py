from src.diagnosis.safety_checks import SafetyCheckEngine


def test_safety_checks_report_provenance_and_failures():
    parsed = {
        "metadata": {
            "quality_report": {"integrity": {"status": "RELIABLE"}},
        },
        "status_messages": [{"time_us": 10, "message": "PreArm: Compass not calibrated"}],
        "errors": [
            {"time_us": 20, "subsystem": 5, "subsystem_name": "FAILSAFE_RADIO", "code": 1},
            {"time_us": 30, "subsystem": 30, "subsystem_name": "INTERNAL_ERROR", "code": 2},
            {"time_us": 40, "subsystem": 12, "subsystem_name": "CRASH_CHECK", "code": 1},
        ],
        "messages": {},
        "parameters": {"COMPASS_USE": 1},
        "parameter_changes": [{"time_us": 50, "name": "ATC_RAT_RLL_P", "old_value": 0.1, "new_value": 0.2}],
    }
    findings = SafetyCheckEngine().evaluate(parsed)
    by_id = {item["check_id"]: item for item in findings}
    assert by_id["prearm_warning"]["status"] == "finding"
    assert by_id["watchdog_or_internal_error"]["severity"] == "critical"
    assert by_id["failsafe_event"]["status"] == "finding"
    assert by_id["configured_sensor_silent"]["status"] == "finding"
    assert by_id["crash_or_impact"]["status"] == "finding"
    assert by_id["crash_or_impact"]["source_url"].startswith("https://")


def test_safety_checks_are_explicit_when_clear():
    parsed = {
        "metadata": {"quality_report": {"integrity": {"status": "RELIABLE"}}},
        "status_messages": [],
        "errors": [],
        "messages": {"MAG": [{}], "GPS": [{}]},
        "parameters": {},
        "parameter_changes": [],
    }
    findings = SafetyCheckEngine().evaluate(parsed)
    assert all(item["status"] == "clear" for item in findings)

