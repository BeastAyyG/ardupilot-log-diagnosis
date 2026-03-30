from src.parser.bin_parser import LogParser


class _FakeMessage:
    def __init__(self, msg_type, data):
        self._msg_type = msg_type
        self._data = data
        for key, value in data.items():
            setattr(self, key, value)

    def get_type(self):
        return self._msg_type

    def to_dict(self):
        return dict(self._data)


class _FakeReader:
    def __init__(self, messages):
        self._messages = list(messages)

    def recv_msg(self):
        if self._messages:
            return self._messages.pop(0)
        return None


def test_parse_valid_bin():
    parser = LogParser("nonexistent_but_valid.BIN")
    parsed = parser.parse()
    assert "metadata" in parsed
    assert "messages" in parsed


def test_parse_corrupted(tmp_path):
    bad_bin = tmp_path / "corrupted.BIN"
    bad_bin.write_bytes(b"BAD_DATA")
    parser = LogParser(str(bad_bin))
    parsed = parser.parse()
    assert parsed["metadata"]["total_messages"] == 0


def test_parse_empty(tmp_path):
    empty_bin = tmp_path / "empty.BIN"
    empty_bin.write_bytes(b"")
    parser = LogParser(str(empty_bin))
    parsed = parser.parse()
    assert parsed["metadata"]["total_messages"] == 0


def test_err_mapping():
    from src.constants import ERR_SUBSYSTEM_MAP

    assert ERR_SUBSYSTEM_MAP[11] == "GPS"
    assert ERR_SUBSYSTEM_MAP[12] == "CRASH_CHECK"


def test_parameter_extraction(monkeypatch):
    fake_messages = [
        _FakeMessage("PARM", {"Name": "BATT_LOW_VOLT", "Value": 10.5, "TimeUS": 1000}),
        _FakeMessage("MSG", {"Message": "ArduCopter 4.5.1", "TimeUS": 2000}),
    ]
    monkeypatch.setattr(
        "src.parser.bin_parser.DFReader.DFReader_binary",
        lambda _filepath: _FakeReader(fake_messages),
    )

    parsed = LogParser("fake.BIN").parse()
    assert parsed["parameters"]["BATT_LOW_VOLT"] == 10.5
    assert parsed["metadata"]["vehicle_type"] == "Copter"
    assert parsed["metadata"]["firmware_version"] == "4.5.1"


def test_mode_changes(monkeypatch):
    fake_messages = [
        _FakeMessage("MODE", {"ModeNum": 6, "Reason": 2, "TimeUS": 1000}),
        _FakeMessage("EV", {"Id": 19, "TimeUS": 2000}),
        _FakeMessage("ERR", {"Subsys": 5, "ECode": 1, "TimeUS": 3000}),
    ]
    monkeypatch.setattr(
        "src.parser.bin_parser.DFReader.DFReader_binary",
        lambda _filepath: _FakeReader(fake_messages),
    )

    parsed = LogParser("fake.BIN").parse()
    assert parsed["mode_changes"][0]["mode_name"] == "RTL"
    assert parsed["events"][0]["name"] == "GPS_LOST"
    assert parsed["errors"][0]["subsystem_name"] == "FAILSAFE_RADIO"


def test_vehicle_detection_from_plane_boot_message(monkeypatch):
    fake_messages = [
        _FakeMessage("MSG", {"Message": "ArduPlane 4.5.0", "TimeUS": 1000}),
    ]
    monkeypatch.setattr(
        "src.parser.bin_parser.DFReader.DFReader_binary",
        lambda _filepath: _FakeReader(fake_messages),
    )

    parsed = LogParser("fake.BIN").parse()
    assert parsed["metadata"]["vehicle_type"] == "Plane"
    assert parsed["metadata"]["firmware_version"] == "4.5.0"


def test_vehicle_detection_from_parameters(monkeypatch):
    fake_messages = [
        _FakeMessage("PARM", {"Name": "SKID_STEER_OUT", "Value": 1, "TimeUS": 1000}),
    ]
    monkeypatch.setattr(
        "src.parser.bin_parser.DFReader.DFReader_binary",
        lambda _filepath: _FakeReader(fake_messages),
    )

    parsed = LogParser("fake.BIN").parse()
    assert parsed["metadata"]["vehicle_type"] == "Rover"


def test_duration_and_message_counts(monkeypatch):
    fake_messages = [
        _FakeMessage("VIBE", {"VibeZ": 10.0, "TimeUS": 1_000_000}),
        _FakeMessage("VIBE", {"VibeZ": 20.0, "TimeUS": 4_000_000}),
    ]
    monkeypatch.setattr(
        "src.parser.bin_parser.DFReader.DFReader_binary",
        lambda _filepath: _FakeReader(fake_messages),
    )

    parsed = LogParser("fake.BIN").parse()
    assert parsed["metadata"]["total_messages"] == 2
    assert parsed["metadata"]["message_types"]["VIBE"] == 2
    assert parsed["metadata"]["duration_sec"] == 3.0
