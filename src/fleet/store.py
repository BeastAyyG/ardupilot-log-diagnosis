"""Small SQLite fleet store with explicit retention and local ownership.

The store persists canonical reports only. It never opens a vehicle connection,
writes parameters, or uploads data. Operators can point it at a removable/local
database and delete records when retention expires.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class FleetStore:
    def __init__(self, database: str | Path = "fleet_reports.sqlite3", *, retention_days: int | None = None, read_only: bool = False):
        self.database = Path(database)
        if not read_only:
            self.database.parent.mkdir(parents=True, exist_ok=True)
        self.retention_days = retention_days
        self.read_only = read_only
        if not read_only:
            self._initialize()

    def _connect(self) -> sqlite3.Connection:
        if self.read_only:
            connection = sqlite3.connect(f"file:{self.database.resolve()}?mode=ro", uri=True)
        else:
            connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS aircraft (
                    aircraft_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    owner TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS flight_reports (
                    report_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    aircraft_id TEXT NOT NULL,
                    filename TEXT,
                    sha256 TEXT,
                    captured_at TEXT,
                    vehicle TEXT,
                    firmware TEXT,
                    report_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(aircraft_id) REFERENCES aircraft(aircraft_id)
                );
                CREATE TABLE IF NOT EXISTS maintenance_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    aircraft_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    note TEXT NOT NULL,
                    event_time TEXT NOT NULL,
                    FOREIGN KEY(aircraft_id) REFERENCES aircraft(aircraft_id)
                );
                CREATE INDEX IF NOT EXISTS idx_flight_aircraft ON flight_reports(aircraft_id, created_at);
                """
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def ensure_aircraft(self, aircraft_id: str, *, display_name: str | None = None, owner: str | None = None) -> None:
        aircraft_id = str(aircraft_id).strip()
        if not aircraft_id or len(aircraft_id) > 128:
            raise ValueError("aircraft_id must be 1-128 characters")
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO aircraft(aircraft_id, display_name, owner, created_at) VALUES (?, ?, ?, ?) ON CONFLICT(aircraft_id) DO UPDATE SET display_name=excluded.display_name, owner=COALESCE(excluded.owner, aircraft.owner)",
                (aircraft_id, display_name or aircraft_id, owner, self._now()),
            )

    def add_report(self, report: dict[str, Any], *, aircraft_id: str = "default", filename: str | None = None) -> int:
        if not isinstance(report, dict) or not report.get("schema_version"):
            raise ValueError("A versioned canonical report is required")
        self.ensure_aircraft(aircraft_id)
        metadata = report.get("metadata", {}) or {}
        hardware = report.get("hardware_report", {}) or {}
        file_info = hardware.get("file", {}) if isinstance(hardware, dict) else {}
        created = self._now()
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO flight_reports(aircraft_id, filename, sha256, captured_at, vehicle, firmware, report_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (aircraft_id, filename or metadata.get("filename"), file_info.get("sha256"), metadata.get("timestamp"), metadata.get("vehicle", metadata.get("vehicle_type")), metadata.get("firmware", hardware.get("metadata", {}).get("firmware_version")), json.dumps(report, sort_keys=True, default=str), created),
            )
            report_id = int(cursor.lastrowid)
        self.apply_retention()
        return report_id

    def list_reports(self, *, aircraft_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 1000))
        query = "SELECT report_id, aircraft_id, filename, sha256, captured_at, vehicle, firmware, created_at, report_json FROM flight_reports"
        parameters: tuple[Any, ...] = ()
        if aircraft_id:
            query += " WHERE aircraft_id = ?"
            parameters = (aircraft_id,)
        query += " ORDER BY created_at DESC LIMIT ?"
        parameters += (limit,)
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["report"] = json.loads(item.pop("report_json"))
            result.append(item)
        return result

    def search_reports(self, *, aircraft_id: str | None = None, vehicle: str | None = None, firmware: str | None = None, filename: str | None = None, min_health: float | None = None, max_health: float | None = None, limit: int = 100) -> list[dict[str, Any]]:
        """Search local canonical reports without exposing raw logs or coordinates."""
        candidates = self.list_reports(aircraft_id=aircraft_id, limit=min(max(int(limit) * 10, 100), 1000))
        result: list[dict[str, Any]] = []
        for item in candidates:
            if vehicle and str(item.get("vehicle", "")).lower() != str(vehicle).lower():
                continue
            if firmware and str(item.get("firmware", "")).lower() != str(firmware).lower():
                continue
            if filename and str(filename).lower() not in str(item.get("filename", "")).lower():
                continue
            score = (item.get("report", {}).get("health_score", {}) or {}).get("score")
            if min_health is not None and (not isinstance(score, (int, float)) or float(score) < float(min_health)):
                continue
            if max_health is not None and (not isinstance(score, (int, float)) or float(score) > float(max_health)):
                continue
            result.append(item)
            if len(result) >= max(1, min(int(limit), 1000)):
                break
        return result

    def add_maintenance(self, aircraft_id: str, event_type: str, note: str, event_time: str | None = None) -> int:
        self.ensure_aircraft(aircraft_id)
        if not event_type or not note:
            raise ValueError("event_type and note are required")
        with self._connect() as connection:
            cursor = connection.execute("INSERT INTO maintenance_events(aircraft_id, event_type, note, event_time) VALUES (?, ?, ?, ?)", (aircraft_id, event_type[:128], note[:4000], event_time or self._now()))
            return int(cursor.lastrowid)

    def list_maintenance(self, aircraft_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return [dict(row) for row in connection.execute("SELECT event_id, aircraft_id, event_type, note, event_time FROM maintenance_events WHERE aircraft_id = ? ORDER BY event_time DESC", (aircraft_id,)).fetchall()]

    def trend(self, aircraft_id: str, *, limit: int = 100) -> dict[str, Any]:
        from src.comparison.trend_analyzer import TrendAnalyzer

        rows = list(reversed(self.list_reports(aircraft_id=aircraft_id, limit=limit)))
        reports = [row["report"] for row in rows]
        if len(reports) < 2:
            return {"schema_version": "trend-report.v2", "status": "insufficient_data", "flights_analyzed": len(reports), "aircraft_id": aircraft_id}
        result = TrendAnalyzer().compare_flights(reports)
        result["aircraft_id"] = aircraft_id
        result["maintenance_events"] = self.list_maintenance(aircraft_id)
        return result

    def apply_retention(self) -> int:
        if self.retention_days is None or self.retention_days <= 0:
            return 0
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM flight_reports WHERE datetime(created_at) < datetime('now', ?)", (f"-{int(self.retention_days)} days",))
            return int(cursor.rowcount)
