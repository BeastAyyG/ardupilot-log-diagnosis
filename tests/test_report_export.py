from pypdf import PdfReader

from src.reporting.report_export import export_pdf


def test_pdf_export_has_expected_sections(tmp_path):
    output = tmp_path / "report.pdf"
    report = {
        "schema_version": "analysis-report.v1",
        "metadata": {"filename": "flight.bin", "vehicle": "Copter"},
        "decision": {"status": "healthy", "top_guess": None, "top_confidence": 0.0},
        "diagnoses": [],
        "hardware_report": {
            "file": {"sha256": "abc"},
            "metadata": {"vehicle_type": "Copter", "firmware_version": "4.5", "duration_sec": 10, "total_messages": 20},
            "system_health": {"error_count": 0, "watchdog_or_internal_error": False},
            "safety_findings": [],
            "sensor_metrics": {},
            "tuning_metrics": {},
        },
    }
    export_pdf(report, output)
    reader = PdfReader(str(output))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert len(reader.pages) == 3
    assert "ArduPilot Flight Analysis Report" in text
    assert "Hardware and Log Quality" in text
