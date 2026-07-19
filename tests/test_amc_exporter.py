from src.export.amc_exporter import AMCExporter


def test_amc_exporter_basic():
    diagnoses = [
        {
            "failure_type": "vibration_high",
            "confidence": 0.85,
            "severity": "critical",
            "detection_method": "rule+ml",
            "evidence": [],
            "recommendation": "Check props",
            "reason_code": "confirmed",
        },
        {
            "failure_type": "pid_tuning_issue",
            "confidence": 0.65,
            "severity": "warning",
            "detection_method": "rule",
            "evidence": [],
            "recommendation": "Run autotune",
            "reason_code": "confirmed",
        },
    ]
    metadata = {"log_file": "test.BIN", "vehicle_type": "Copter", "quality_report": {"overall_status": "RELIABLE"}}
    exporter = AMCExporter()
    res = exporter.export(diagnoses, metadata, parameter_warnings=[])
    assert res["quality_grade"] == "RELIABLE"
    assert len(res["workflow_steps"]) == 2
    assert res["workflow_steps"][0]["step_id"] == "10_filter_tuning"
    assert res["workflow_steps"][1]["step_id"] == "15_rate_pid_tuning"

    json_out = exporter.export_json(diagnoses, metadata)
    assert "10_filter_tuning" in json_out
