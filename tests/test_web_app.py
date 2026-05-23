from __future__ import annotations

import asyncio
import io
import json

import pytest
from starlette.datastructures import UploadFile
from starlette.responses import JSONResponse

fastapi = pytest.importorskip("fastapi")

from src.web import app as web_app


class _FakeParser:
    def __init__(self, _path: str):
        self.path = _path

    def parse(self):
        return {
            "messages": {
                "VIBE": [],
                "GPS": [
                    # Status=2 (2-D fix) — should NOT count as TTFF
                    {"TimeUS": 2_000_000, "Lat": 123456789, "Lng": 987654321, "Alt": 10,
                     "HDop": 1.5, "NSats": 9, "Status": 2},
                    # Status=3 (3-D fix) — TTFF should be the offset of this message
                    {"TimeUS": 3_500_000, "Lat": 123456999, "Lng": 987654111, "Alt": 12,
                     "HDop": 1.7, "NSats": 8, "Status": 3},
                ],
            },
            "errors": [],
            "mode_changes": [],
            "events": [],
        }


class _FakePipeline:
    def extract(self, _parsed):
        return {
            "_metadata": {
                "duration_sec": 1.5,
                "vehicle_type": "QuadPlane",
            }
        }


class _FakeHybridEngine:
    def __init__(self):
        self.last_explain_data = {"rule": [], "ml": [], "anomaly": {"is_anomaly": False}}

    def diagnose(self, _features):
        return [
            {
                "failure_type": "gps_quality_poor",
                "confidence": 0.88,
                "severity": "warning",
                "detection_method": "ml",
                "evidence": [],
                "recommendation": "Inspect GPS health.",
                "reason_code": "confirmed",
            }
        ]


class _FakeRuleEngine:
    def diagnose(self, _features):
        return [
            {
                "failure_type": "compass_interference",
                "confidence": 0.8,
                "severity": "warning",
                "detection_method": "rule",
                "evidence": [],
                "recommendation": "Check compass placement.",
                "reason_code": "confirmed",
            }
        ]


def _make_upload(payload: bytes, filename: str = "flight.BIN") -> UploadFile:
    return UploadFile(file=io.BytesIO(payload), filename=filename)


def _response_to_dict(response) -> dict:
    """Extract dict from either AnalysisResponse (pydantic) or JSONResponse."""
    if isinstance(response, JSONResponse):
        return json.loads(response.body)
    # Pydantic model (AnalysisResponse)
    return response.model_dump()


def test_api_analyze_handles_gps_without_vibe(monkeypatch):
    monkeypatch.setattr(web_app, "_rule_engine", None)  # reset singleton so monkeypatch takes effect
    monkeypatch.setattr(web_app, "LogParser", _FakeParser)
    monkeypatch.setattr(web_app, "FeaturePipeline", _FakePipeline)
    monkeypatch.setattr(web_app, "HybridEngine", _FakeHybridEngine)
    monkeypatch.setattr(web_app, "RuleEngine", _FakeRuleEngine)

    response = asyncio.run(web_app.analyze_log(_make_upload(b"abc")))
    payload = _response_to_dict(response)

    # GPS path time series
    assert payload["time_series"]["gps"][0]["t"] == 0.0

    # Metadata
    assert payload["metadata"]["vehicle"] == "QuadPlane"

    # GPS quality — summary stats
    assert payload["gps_quality"]["avg_hdop"] == 1.6
    assert payload["gps_quality"]["min_satellites"] == 8

    # GPS quality — time-series lengths (two GPS messages, step=1)
    assert len(payload["gps_quality"]["hdop"]) == 2
    assert len(payload["gps_quality"]["sat_count"]) == 2
    assert len(payload["gps_quality"]["fix_type"]) == 2

    # GPS quality — fix_type values: first msg Status=2, second Status=3
    assert payload["gps_quality"]["fix_type"][0]["v"] == 2
    assert payload["gps_quality"]["fix_type"][1]["v"] == 3

    # GPS quality — TTFF: first 3-D fix is the second message at t=1.5 s
    # (TimeUS 3_500_000 − 2_000_000) / 1e6 = 1.5 s
    assert payload["gps_quality"]["ttff_sec"] == 1.5


def test_api_rule_output_only_is_string(monkeypatch):
    monkeypatch.setattr(web_app, "_rule_engine", None)  # reset singleton so monkeypatch takes effect
    monkeypatch.setattr(web_app, "LogParser", _FakeParser)
    monkeypatch.setattr(web_app, "FeaturePipeline", _FakePipeline)
    monkeypatch.setattr(web_app, "HybridEngine", _FakeHybridEngine)
    monkeypatch.setattr(web_app, "RuleEngine", _FakeRuleEngine)

    response = asyncio.run(web_app.analyze_log(_make_upload(b"abc")))
    payload = _response_to_dict(response)

    assert payload["rule_output_only"] == "compass_interference"
    assert isinstance(payload["rule_output_only"], str)


def test_api_rejects_oversized_upload(monkeypatch):
    monkeypatch.setattr(web_app, "_rule_engine", None)  # reset singleton so monkeypatch takes effect
    monkeypatch.setattr(web_app, "MAX_UPLOAD_BYTES", 4)

    class _ExplodingParser:
        def __init__(self, _path: str):
            raise AssertionError("parser should not run for oversized uploads")

    monkeypatch.setattr(web_app, "LogParser", _ExplodingParser)

    response = asyncio.run(web_app.analyze_log(_make_upload(b"12345")))
    payload = _response_to_dict(response)

    assert response.status_code == 413
    assert "exceeds" in payload["error"]


def test_api_ttff_none_when_no_fix(monkeypatch):
    """TTFF must be None when no GPS message ever reaches Status >= 3."""

    class _NoFixParser:
        def __init__(self, _path: str):
            pass

        def parse(self):
            return {
                "messages": {
                    "VIBE": [],
                    "GPS": [
                        {"TimeUS": 1_000_000, "Lat": 0, "Lng": 0, "Alt": 0,
                         "HDop": 3.0, "NSats": 3, "Status": 1},
                        {"TimeUS": 2_000_000, "Lat": 0, "Lng": 0, "Alt": 0,
                         "HDop": 2.8, "NSats": 4, "Status": 2},
                    ],
                },
                "errors": [],
                "mode_changes": [],
                "events": [],
            }

    class _NoFixPipeline:
        def extract(self, _parsed):
            return {"_metadata": {"duration_sec": 1.0, "vehicle_type": "Copter"}}

    monkeypatch.setattr(web_app, "_rule_engine", None)  # reset singleton so monkeypatch takes effect
    monkeypatch.setattr(web_app, "LogParser", _NoFixParser)
    monkeypatch.setattr(web_app, "FeaturePipeline", _NoFixPipeline)
    monkeypatch.setattr(web_app, "HybridEngine", _FakeHybridEngine)
    monkeypatch.setattr(web_app, "RuleEngine", _FakeRuleEngine)

    response = asyncio.run(web_app.analyze_log(_make_upload(b"abc")))
    payload = _response_to_dict(response)

    assert payload["gps_quality"]["ttff_sec"] is None


def test_api_gps_quality_safe_defaults_when_no_gps(monkeypatch):
    """gps_quality must contain empty lists and zero stats when GPS messages are absent."""

    class _NoGpsParser:
        def __init__(self, _path: str):
            pass

        def parse(self):
            return {
                "messages": {"VIBE": [], "GPS": []},
                "errors": [],
                "mode_changes": [],
                "events": [],
            }

    class _NoGpsPipeline:
        def extract(self, _parsed):
            return {"_metadata": {"duration_sec": 5.0, "vehicle_type": "Copter"}}

    monkeypatch.setattr(web_app, "_rule_engine", None)  # reset singleton so monkeypatch takes effect
    monkeypatch.setattr(web_app, "LogParser", _NoGpsParser)
    monkeypatch.setattr(web_app, "FeaturePipeline", _NoGpsPipeline)
    monkeypatch.setattr(web_app, "HybridEngine", _FakeHybridEngine)
    monkeypatch.setattr(web_app, "RuleEngine", _FakeRuleEngine)

    response = asyncio.run(web_app.analyze_log(_make_upload(b"abc")))
    payload = _response_to_dict(response)

    gq = payload["gps_quality"]
    assert gq["hdop"] == []
    assert gq["sat_count"] == []
    assert gq["fix_type"] == []
    assert gq["avg_hdop"] == 0.0
    assert gq["min_satellites"] == 0
    assert gq["ttff_sec"] is None