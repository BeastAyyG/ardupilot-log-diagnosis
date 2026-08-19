from pathlib import Path

from pymavlink import mavutil

from src.parser.tlog_parser import TLogParser


class _FakeMessage:
    def __init__(self, name: str, payload: dict):
        self._name = name
        self._payload = payload

    def get_type(self):
        return self._name

    def to_dict(self):
        return dict(self._payload)


class _FakeConnection:
    def __init__(self, messages):
        self._messages = iter(messages)

    def recv_match(self, blocking=False):
        return next(self._messages, None)

    def close(self):
        return None


def test_tlog_time_usec_is_not_rescaled(monkeypatch, tmp_path: Path):
    path = tmp_path / "flight.tlog"
    path.write_bytes(b"not-a-real-tlog")
    messages = [
        _FakeMessage("GPS_RAW_INT", {"time_usec": 500_000}),
        _FakeMessage("GPS_RAW_INT", {"time_usec": 1_500_000}),
    ]
    monkeypatch.setattr(mavutil, "mavlink_connection", lambda *args, **kwargs: _FakeConnection(messages))

    parsed = TLogParser(str(path)).parse()

    assert parsed["metadata"]["parse_complete"] is True
    assert parsed["metadata"]["duration_sec"] == 1.0
    assert parsed["messages"]["GPS"][0]["TimeUS"] == 500_000


def test_tlog_common_mavlink_streams_are_normalized(monkeypatch, tmp_path: Path):
    path = tmp_path / "normalized.tlog"
    path.write_bytes(b"not-a-real-tlog")
    messages = [
        _FakeMessage(
            "GPS_RAW_INT",
            {
                "time_usec": 1_000_000,
                "lat": 120000000,
                "lon": 770000000,
                "alt": 12500,
                "eph": 120,
                "satellites_visible": 12,
                "fix_type": 3,
            },
        ),
        _FakeMessage(
            "BATTERY_STATUS",
            {"time_boot_ms": 1100, "voltages": [16000], "current_battery": 250},
        ),
    ]
    monkeypatch.setattr(mavutil, "mavlink_connection", lambda *args, **kwargs: _FakeConnection(messages))

    parsed = TLogParser(str(path)).parse()

    assert parsed["messages"]["GPS"][0]["Lat"] == 12.0
    assert parsed["messages"]["GPS"][0]["HDop"] == 1.2
    assert parsed["messages"]["GPS"][0]["lat"] == 120000000
    assert parsed["messages"]["BAT"][0]["Volt"] == 16.0
    assert parsed["messages"]["BAT"][0]["Curr"] == 2.5


def test_tlog_mixed_epoch_and_boot_clocks_are_aligned(monkeypatch, tmp_path: Path):
    path = tmp_path / "mixed-clocks.tlog"
    path.write_bytes(b"not-a-real-tlog")
    messages = [
        _FakeMessage("GPS_RAW_INT", {"time_usec": 1_700_000_000_000_000, "lat": 120000000, "lon": 770000000}),
        _FakeMessage("HEARTBEAT", {"time_boot_ms": 2_000, "custom_mode": 3}),
    ]
    monkeypatch.setattr(mavutil, "mavlink_connection", lambda *args, **kwargs: _FakeConnection(messages))
    parsed = TLogParser(str(path)).parse()
    assert parsed["metadata"]["duration_sec"] == 0.0
    assert parsed["messages"]["GPS"][0]["TimeUS"] == 0
    assert parsed["messages"]["MODE"][0]["TimeUS"] == 0


def test_tlog_populates_canonical_event_and_parameter_side_channels(monkeypatch, tmp_path: Path):
    path = tmp_path / "context.tlog"
    path.write_bytes(b"not-a-real-tlog")
    messages = [
        _FakeMessage("HEARTBEAT", {"time_boot_ms": 1000, "custom_mode": 3}),
        _FakeMessage("HEARTBEAT", {"time_boot_ms": 2000, "custom_mode": 3}),
        _FakeMessage("STATUSTEXT", {"time_boot_ms": 2500, "severity": 4, "text": "PreArm: compass"}),
        _FakeMessage("PARAM_VALUE", {"time_boot_ms": 3000, "param_id": "COMPASS_USE", "param_value": 1.0}),
        _FakeMessage("PARAM_VALUE", {"time_boot_ms": 4000, "param_id": "COMPASS_USE", "param_value": 0.0}),
    ]
    monkeypatch.setattr(mavutil, "mavlink_connection", lambda *args, **kwargs: _FakeConnection(messages))

    parsed = TLogParser(str(path)).parse()

    assert len(parsed["mode_changes"]) == 1
    assert parsed["mode_changes"][0]["mode"] == 3
    assert parsed["mode_changes"][0]["mode_name"] == "MAV_CUSTOM_MODE_3"
    assert parsed["status_messages"][0]["message"] == "PreArm: compass"
    assert parsed["parameters"]["COMPASS_USE"] == 0.0
    assert parsed["parameter_changes"][0]["old_value"] == 1.0


def test_tlog_decodes_null_padded_bytes_for_text_and_parameters(monkeypatch, tmp_path: Path):
    path = tmp_path / "bytes.tlog"
    path.write_bytes(b"not-a-real-tlog")
    messages = [
        _FakeMessage("STATUSTEXT", {"time_boot_ms": 1000, "text": b"PreArm: GPS\x00"}),
        _FakeMessage("PARAM_VALUE", {"time_boot_ms": 1000, "param_id": b"GPS_TYPE\x00", "param_value": 1.0}),
    ]
    monkeypatch.setattr(mavutil, "mavlink_connection", lambda *args, **kwargs: _FakeConnection(messages))
    parsed = TLogParser(str(path)).parse()
    assert parsed["status_messages"][0]["message"] == "PreArm: GPS"
    assert parsed["parameters"]["GPS_TYPE"] == 1.0
