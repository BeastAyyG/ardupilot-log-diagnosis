from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from src.web import app as web_app


def test_dashboard_live_stop_forwards_the_active_auth_token_and_avoids_stale_model_claims():
    page = (web_app.WEB_DIR / "index.html").read_text(encoding="utf-8")

    assert "const stopToken = _reconnectToken ?? document.getElementById('live-auth-token').value.trim();" in page
    assert "`/api/live/stop?token=${encodeURIComponent(stopToken)}`" in page
    assert "if (!res.ok)" in page
    assert "Hybrid Rule/ML Engine" in page
    assert "XGBOOST" not in page
    assert "60+ TELEMETRY FEATURES" not in page


def test_dashboard_upload_contract_matches_supported_log_formats():
    page = (web_app.WEB_DIR / "index.html").read_text(encoding="utf-8")

    for extension in (".BIN", ".LOG", ".ULG", ".ULOG", ".TLOG", ".BBL", ".BFL"):
        assert extension in page
    assert "const supportedExtensions = ['.bin', '.log', '.ulg', '.ulog', '.tlog', '.bbl', '.bfl'];" in page
    assert "Drag &amp; Drop a flight log" in page


def test_upload_temp_suffix_preserves_generic_adapters():
    assert web_app._flight_log_temp_suffix("flight.bin") == ".bin"
    assert web_app._flight_log_temp_suffix("flight.ulg") == ".ulg"
    assert web_app._flight_log_temp_suffix("flight.ulog") == ".ulog"
    assert web_app._flight_log_temp_suffix("flight.tlog") == ".tlog"
    assert web_app._flight_log_temp_suffix("flight.exe") == ".bin"


def test_visualization_preserves_decimal_degree_coordinates_from_generic_adapters():
    parsed = {
        "messages": {
            "GPS": [
                {"TimeUS": 0, "Lat": 12.0, "Lng": 77.0, "Alt": 100.0, "HDop": 1.0, "NSats": 12, "Status": 3},
            ]
        },
        "errors": [],
        "mode_changes": [],
        "events": [],
    }
    series, _events, _quality = web_app._build_visualization_data(parsed, {"_metadata": {"duration_sec": 0.0}})
    assert series["gps"][0]["lat"] == 12.0
    assert series["gps"][0]["lng"] == 77.0


def test_api_preserves_tlog_suffix_for_adapter_detection(monkeypatch):
    captured = {}

    def fake_analysis(path: str, filename: str):
        captured["suffix"] = Path(path).suffix
        return {
            "schema_version": "analysis-response.v1",
            "metadata": {"filename": filename, "duration": 0.0, "vehicle": "MAVLink", "file_format": {"format": "mavlink_tlog"}, "sha256": None},
            "features": {}, "diagnoses": [], "decision": {}, "parameter_warnings": [], "explain_data": {"decision": {}},
            "time_series": {"gps": [], "vibe": []}, "timeline_events": [],
            "gps_quality": {"hdop": [], "sat_count": [], "fix_type": [], "avg_hdop": 0.0, "min_satellites": 0, "ttff_sec": None},
            "rule_output_only": "nominal", "rule_output_diagnoses": [], "hardware_report": {}, "health_score": {},
        }

    monkeypatch.setattr(web_app, "_analyze_temp_log", fake_analysis)
    response = TestClient(web_app.app).post("/api/analyze", files={"file": ("empty.tlog", b"", "application/octet-stream")})
    assert response.status_code == 200
    assert captured["suffix"] == ".tlog"


class _DummyParser:
    def __init__(self, _filepath: str):
        pass

    def parse(self) -> dict:
        return {
            "messages": {
                "GPS": [
                    {
                        "Lat": 374221234,
                        "Lng": -1220845678,
                        "Alt": 25,
                        "TimeUS": 2_000_000,
                        "HDop": 1.2,
                        "NSats": 10,
                        "Status": 3,
                    }
                ],
                "VIBE": [],
            },
            "errors": [],
            "events": [],
            "mode_changes": [],
        }


class _DummyPipeline:
    def extract(self, _parsed: dict) -> dict:
        return {
            "_metadata": {
                "duration_sec": 12.0,
                "vehicle_type": "Copter",
            }
        }


class _DummyHybridEngine:
    def __init__(self):
        self.last_explain_data = {"rule": [], "ml": [], "anomaly": {"is_anomaly": False}}

    def diagnose(self, _features: dict) -> list[dict]:
        return [
            {
                "failure_type": "gps_quality_poor",
                "confidence": 0.71,
                "severity": "warning",
                "detection_method": "rule",
                "evidence": [],
                "recommendation": "Review GPS quality.",
                "reason_code": "uncertain",
            }
        ]


class _DummyRuleEngine:
    def diagnose(self, _features: dict) -> list[dict]:
        return [
            {
                "failure_type": "gps_quality_poor",
                "confidence": 0.66,
                "severity": "warning",
                "detection_method": "rule",
                "evidence": [],
                "recommendation": "Review GPS quality.",
                "reason_code": "uncertain",
            }
        ]


def test_api_analyze_handles_gps_only_logs(monkeypatch):
    monkeypatch.setattr(web_app, "_rule_engine", None)  # reset singleton so monkeypatch takes effect
    monkeypatch.setattr(web_app, "LogParser", _DummyParser)
    monkeypatch.setattr(web_app, "FeaturePipeline", _DummyPipeline)
    monkeypatch.setattr(web_app, "HybridEngine", _DummyHybridEngine)
    monkeypatch.setattr(web_app, "RuleEngine", _DummyRuleEngine)
    monkeypatch.setattr(
        web_app,
        "evaluate_decision",
        lambda _diagnoses: {
            "status": "uncertain",
            "requires_human_review": True,
            "top_guess": "gps_quality_poor",
            "top_confidence": 0.71,
            "rationale": ["GPS quality degraded."],
            "ranked_subsystems": [],
        },
    )

    client = TestClient(web_app.app)
    response = client.post(
        "/api/analyze",
        files={"file": ("gps_only.bin", b"dummy", "application/octet-stream")},
    )

    assert response.status_code == 200
    data = response.json()

    # Core metadata
    assert data["metadata"]["filename"] == "gps_only.bin"
    assert data["decision"]["top_guess"] == "gps_quality_poor"
    assert data["explain_data"]["decision"] == data["decision"]
    assert data["rule_output_only"] == "gps_quality_poor"

    # GPS path time series
    assert data["time_series"]["gps"][0]["t"] == 0.0

    # GPS quality — summary stats
    assert data["gps_quality"]["avg_hdop"] == 1.2
    assert data["gps_quality"]["min_satellites"] == 10

    # GPS quality — time-series lengths
    assert len(data["gps_quality"]["hdop"]) == 1
    assert len(data["gps_quality"]["sat_count"]) == 1
    assert len(data["gps_quality"]["fix_type"]) == 1

    # GPS quality — fix_type value for the single message (Status=3)
    assert data["gps_quality"]["fix_type"][0]["v"] == 3

    # GPS quality — TTFF: single message already has Status=3, so offset is 0.0 s
    assert data["gps_quality"]["ttff_sec"] == 0.0


def test_api_analyze_rejects_unusable_logs_before_diagnosis(monkeypatch):
    class InvalidParser:
        def __init__(self, _filepath: str):
            pass

        def parse(self) -> dict:
            return {"messages": {}, "metadata": {"duration_sec": 0.0}}

    class FailedPipeline:
        def extract(self, _parsed: dict) -> dict:
            return {
                "_metadata": {
                    "duration_sec": 0.0,
                    "extraction_success": False,
                    "quality_report": {
                        "overall_status": "UNSUPPORTED",
                    },
                }
            }

    class UnexpectedHybridEngine:
        def __init__(self):
            raise AssertionError("diagnosis must not run for an unusable log")

    monkeypatch.setattr(web_app, "LogParser", InvalidParser)
    monkeypatch.setattr(web_app, "FeaturePipeline", FailedPipeline)
    monkeypatch.setattr(web_app, "HybridEngine", UnexpectedHybridEngine)

    client = TestClient(web_app.app)
    response = client.post(
        "/api/analyze",
        files={"file": ("corrupt.bin", b"not a flight log", "application/octet-stream")},
    )

    assert response.status_code == 422
    assert "could not be parsed" in response.json()["error"]
    assert response.json()["quality_report"]["overall_status"] == "UNSUPPORTED"
