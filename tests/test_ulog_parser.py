from src.parser.ulog_parser import ULogParser


class _FakeDataset:
    def __init__(self, name, data):
        self.name = name
        self.data = data


class _FakeULog:
    def __init__(self, _path):
        self.data_list = [
            _FakeDataset("vehicle_status", {"timestamp": [1_000_000, 2_000_000], "nav_state": [3, 3]}),
            _FakeDataset("log_message", {"timestamp": [1_500_000], "message": ["PreArm: compass"], "severity": [4]}),
            _FakeDataset("parameter_update", {"timestamp": [1_000_000, 2_000_000], "parameter_name": ["COMPASS_USE", "COMPASS_USE"], "value": [1.0, 0.0]}),
        ]


def test_ulog_populates_canonical_event_and_parameter_side_channels(monkeypatch, tmp_path):
    import pyulog

    path = tmp_path / "context.ulg"
    path.write_bytes(b"ULog" + b"\x00" * 10)
    monkeypatch.setattr(pyulog, "ULog", _FakeULog)

    parsed = ULogParser(str(path)).parse()

    assert len(parsed["mode_changes"]) == 1
    assert parsed["mode_changes"][0]["mode"] == 3
    assert parsed["mode_changes"][0]["mode_name"] == "PX4_NAV_STATE_3"
    assert parsed["status_messages"][0]["message"] == "PreArm: compass"
    assert parsed["parameters"]["COMPASS_USE"] == 0.0
    assert parsed["parameter_changes"][0]["old_value"] == 1.0


def test_ulog_common_rows_are_normalized():
    gps = ULogParser._normalise_row(
        "GPS",
        {
            "lat": 120000000,
            "lon": 770000000,
            "alt": 12500,
            "eph": 1.2,
            "satellites_used": 11,
            "fix_type": 3,
        },
    )
    assert gps["Lat"] == 12.0
    assert gps["Lng"] == 77.0
    assert gps["Alt"] == 12.5
    assert gps["HDop"] == 1.2
    assert gps["Status"] == 3

    battery = ULogParser._normalise_row("BAT", {"voltage_v": 15.8, "current_a": 2.4})
    assert battery["Volt"] == 15.8
    assert battery["Curr"] == 2.4


def test_ulog_quaternion_is_converted_to_attitude_degrees():
    attitude = ULogParser._normalise_row("ATT", {"q[0]": 1.0, "q[1]": 0.0, "q[2]": 0.0, "q[3]": 0.0})
    assert attitude["Roll"] == 0.0
    assert attitude["Pitch"] == 0.0
    assert attitude["Yaw"] == 0.0
    assert attitude["DesRoll"] == 0.0


def test_ulog_text_and_parameter_fields_decode_bytes():
    message = ULogParser._normalise_row("MSG", {"message": b"PreArm: GPS\x00"})
    parameter = ULogParser._normalise_row("PARM", {"parameter_name": b"GPS_TYPE\x00", "value": 1.0})
    assert message["Message"] == "PreArm: GPS"
    assert parameter["Name"] == "GPS_TYPE"
