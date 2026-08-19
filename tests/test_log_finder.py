from __future__ import annotations

from pathlib import Path

import pytest

from src.reporting.log_finder import find_logs


def test_log_finder_indexes_supported_logs_and_groups_metadata(tmp_path: Path):
    source = Path(__file__).parents[1] / "sample.bin"
    (tmp_path / "flight.bin").write_bytes(source.read_bytes())
    result = find_logs(tmp_path, hash_files=True)
    assert result["schema_version"] == "log-index.v1"
    assert result["entry_count"] == 1
    item = result["entries"][0]
    assert item["format"]["format"] == "ardupilot_bin"
    assert item["metadata"]["vehicle_type"] == "Copter"
    assert item["configuration_key"]
    assert len(item["format"]["sha256"]) == 64
    assert result["read_only"] is True


def test_log_finder_is_bounded_and_can_retain_unsupported_inputs(tmp_path: Path):
    (tmp_path / "unknown.bin").write_bytes(b"not a dataflash log")
    (tmp_path / "second.bin").write_bytes(b"not a dataflash log")
    result = find_logs(tmp_path, parse_metadata=False, include_unsupported=True, max_files=1)
    assert result["truncated"] is True
    assert result["candidate_count"] == 2
    assert result["scanned_candidates"] == 1
    assert result["entry_count"] == 1
    assert result["entries"][0]["status"] == "unsupported_optional"
    with pytest.raises(ValueError):
        find_logs(tmp_path / "missing")
