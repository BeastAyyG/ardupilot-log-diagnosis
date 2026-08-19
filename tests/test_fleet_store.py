from pathlib import Path

from src.fleet.store import FleetStore


def _report(name: str):
    return {"schema_version": "analysis-report.v1", "metadata": {"filename": name, "vehicle": "Copter", "firmware": "4.5"}, "decision": {"status": "healthy"}, "features": {"vibe_z_mean": 1.0}, "hardware_report": {"file": {"sha256": name}, "metadata": {"firmware_version": "4.5"}}}


def test_fleet_store_persists_reports_and_maintenance(tmp_path: Path):
    store = FleetStore(tmp_path / "fleet.sqlite3")
    first = store.add_report(_report("one.bin"), aircraft_id="uav-1")
    second = store.add_report(_report("two.bin"), aircraft_id="uav-1")
    assert first != second
    assert len(store.list_reports(aircraft_id="uav-1")) == 2
    event = store.add_maintenance("uav-1", "propeller", "Replaced damaged propeller")
    assert event > 0
    trend = store.trend("uav-1")
    assert trend["flights_analyzed"] == 2
    assert trend["maintenance_events"]


def test_fleet_search_and_read_only_connection(tmp_path: Path):
    database = tmp_path / "fleet.sqlite3"
    store = FleetStore(database)
    report = _report("health.bin")
    report["health_score"] = {"score": 92}
    store.add_report(report, aircraft_id="uav-1")
    rows = store.search_reports(vehicle="Copter", min_health=90)
    assert len(rows) == 1
    readonly = FleetStore(database, read_only=True)
    assert len(readonly.list_reports()) == 1
