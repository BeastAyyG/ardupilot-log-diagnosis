from pathlib import Path

from pymavlink import DFReader

from src.parser.text_parser import TextLogParser


class _FakeMessage:
    def __init__(self, name: str, payload: dict):
        self._name = name
        self._payload = payload

    def get_type(self):
        return self._name

    def to_dict(self):
        return dict(self._payload)


class _FakeReader:
    def __init__(self, _path):
        self._messages = iter(
            [
                _FakeMessage("ERR", {"TimeUS": 1_000_000, "Subsys": 3, "ECode": 99}),
                _FakeMessage("MODE", {"TimeUS": 2_000_000, "Mode": "3"}),
            ]
        )

    def recv_msg(self):
        return next(self._messages, None)

    def close(self):
        return None


def test_text_parser_normalizes_error_labels_and_numeric_modes(monkeypatch, tmp_path: Path):
    path = tmp_path / "flight.log"
    path.write_text("FMT, 1, 2, 3", encoding="ascii")
    monkeypatch.setattr(DFReader, "DFReader_text", _FakeReader)
    parsed = TextLogParser(str(path)).parse()
    assert parsed["errors"][0]["code_name"] == "compass_interference"
    assert parsed["mode_changes"][0]["mode"] == 3
    assert parsed["mode_changes"][0]["mode_name"] == "Auto"
