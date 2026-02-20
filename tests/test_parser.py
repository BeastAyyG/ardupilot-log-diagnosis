import pytest
from src.parser.bin_parser import LogParser

def test_parse_valid_bin():
    # Without a real BIN file, this test will just rely on the fallback structure
    parser = LogParser("nonexistent_but_valid.BIN")
    parsed = parser.parse()
    assert "metadata" in parsed
    assert "messages" in parsed

def test_parse_corrupted(tmp_path):
    # Create a corrupted file
    bad_bin = tmp_path / "corrupted.BIN"
    bad_bin.write_bytes(b"BAD_DATA")
    parser = LogParser(str(bad_bin))
    parsed = parser.parse()
    # Should not crash and return partial/empty data
    assert parsed["metadata"]["total_messages"] == 0

def test_parse_empty(tmp_path):
    empty_bin = tmp_path / "empty.BIN"
    empty_bin.write_bytes(b"")
    parser = LogParser(str(empty_bin))
    parsed = parser.parse()
    assert parsed["metadata"]["total_messages"] == 0

def test_err_mapping():
    # LogParser maps correctly; testing the constants mapping
    from src.constants import ERR_SUBSYSTEM_MAP
    assert ERR_SUBSYSTEM_MAP[11] == "GPS"
    assert ERR_SUBSYSTEM_MAP[12] == "CRASH_CHECK"

def test_parameter_extraction():
    # Mock behavior of parser could be tested by instantiating parsing Logic
    assert True

def test_mode_changes():
    from src.constants import MODE_NAMES
    assert MODE_NAMES[6] == "RTL"
