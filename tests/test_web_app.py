from __future__ import annotations

import asyncio
import io
import json

import pytest
from starlette.datastructures import UploadFile

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
                    {"TimeUS": 2_000_000, "Lat": 123456789, "Lng": 987654321, "Alt": 10},
                    {"TimeUS": 3_500_000, "Lat": 123456999, "Lng": 987654111, "Alt": 12},
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


def test_api_analyze_handles_gps_without_vibe(monkeypatch):
    monkeypatch.setattr(web_app, "LogParser", _FakeParser)
    monkeypatch.setattr(web_app, "FeaturePipeline", _FakePipeline)
    monkeypatch.setattr(web_app, "HybridEngine", _FakeHybridEngine)
    monkeypatch.setattr(web_app, "RuleEngine", _FakeRuleEngine)

    response = asyncio.run(web_app.analyze_log(_make_upload(b"abc")))
    payload = json.loads(response.body)

    assert response.status_code == 200
    assert payload["time_series"]["gps"][0]["t"] == 0.0
    assert payload["metadata"]["vehicle"] == "QuadPlane"


def test_api_rule_output_only_is_string(monkeypatch):
    monkeypatch.setattr(web_app, "LogParser", _FakeParser)
    monkeypatch.setattr(web_app, "FeaturePipeline", _FakePipeline)
    monkeypatch.setattr(web_app, "HybridEngine", _FakeHybridEngine)
    monkeypatch.setattr(web_app, "RuleEngine", _FakeRuleEngine)

    response = asyncio.run(web_app.analyze_log(_make_upload(b"abc")))
    payload = json.loads(response.body)

    assert response.status_code == 200
    assert payload["rule_output_only"] == "compass_interference"
    assert isinstance(payload["rule_output_only"], str)


def test_api_rejects_oversized_upload(monkeypatch):
    monkeypatch.setattr(web_app, "MAX_UPLOAD_BYTES", 4)

    class _ExplodingParser:
        def __init__(self, _path: str):
            raise AssertionError("parser should not run for oversized uploads")

    monkeypatch.setattr(web_app, "LogParser", _ExplodingParser)

    response = asyncio.run(web_app.analyze_log(_make_upload(b"12345")))
    payload = json.loads(response.body)

    assert response.status_code == 413
    assert "exceeds" in payload["error"]
