import asyncio
import io

from starlette.datastructures import UploadFile

from src.web import app as web_app


def test_api_hardware_report_is_read_only(monkeypatch):
    class FakeParser:
        def __init__(self, _path):
            pass

        def parse(self):
            return {
                "metadata": {"vehicle_type": "Copter", "message_types": {"VIBE": 1}, "total_messages": 1},
                "messages": {"VIBE": [{}]},
                "parameters": {},
                "errors": [],
                "events": [],
                "mode_changes": [],
                "status_messages": [],
            }

    monkeypatch.setattr(web_app, "LogParser", FakeParser)
    upload = UploadFile(file=io.BytesIO(b"payload"), filename="flight.bin")
    response = asyncio.run(web_app.hardware_report(upload))
    assert response["schema_version"] == "hardware-report.v1"
    assert response["tuning_metrics"]["write_parameters"] is False

