from __future__ import annotations

from fastapi.testclient import TestClient

from src.web import app as web_app


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