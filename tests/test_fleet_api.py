import asyncio

from src.web import app as web_app


def _report():
    return {"schema_version": "analysis-report.v1", "metadata": {"filename": "one.bin", "vehicle": "Copter", "firmware": "4.5"}, "decision": {"status": "healthy"}, "features": {"vibe_z_mean": 1.0}, "hardware_report": {"metadata": {"firmware_version": "4.5"}}}


def test_fleet_api_round_trip(monkeypatch, tmp_path):
    monkeypatch.setenv("ARDUPILOT_FLEET_DB", str(tmp_path / "fleet.sqlite3"))
    added = asyncio.run(web_app.fleet_add_report({"aircraft_id": "uav-1", "report": _report()}))
    assert added["stored_locally"] is True
    listed = asyncio.run(web_app.fleet_list_reports("uav-1", 10))
    assert len(listed["reports"]) == 1
    event = asyncio.run(web_app.fleet_maintenance({"aircraft_id": "uav-1", "event_type": "inspection", "note": "Checked"}))
    assert event["event_id"] > 0
    trend = asyncio.run(web_app.fleet_trend("uav-1", 10))
    assert trend["flights_analyzed"] == 1
