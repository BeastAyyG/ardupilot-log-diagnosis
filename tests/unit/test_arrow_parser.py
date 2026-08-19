import struct

import pyarrow as pa
import pytest
from pyarrow import ipc

from src.core.ingestion.arrow_parser import parse_arrow
from src.core.ingestion.dataflash_arrow import (
    DuplicateDataFlashFormat,
    FastLogParser,
    TruncatedDataFlash,
    UnsafeDataFlashPath,
    UnsupportedFormatCode,
)


def test_parse_arrow_reflects_message_field_and_fmt(tmp_path):
    table = pa.table(
        {
            "Type": ["FMT", "ATT", "VIBE", "ATT"],
            "Name": ["ATT", None, None, None],
            "Columns": ["TimeUS,Roll", None, None, None],
            "TimeUS": [None, 1, 2, 3],
            "Roll": [None, 10.0, None, 11.0],
            "VibeZ": [None, None, 22.0, None],
        }
    )
    path = tmp_path / "telemetry.arrow"
    with pa.OSFile(str(path), "wb") as sink, ipc.new_file(sink, table.schema) as writer:
        writer.write_table(table)

    result = parse_arrow(path, ("ATT", "VIBE", "FMT"))

    assert result.available_messages == ("ATT", "FMT", "VIBE")
    assert result.table("ATT").num_rows == 2
    assert result.table("VIBE").num_rows == 1
    assert result.format_fields["ATT"] == ("TimeUS", "Roll")
    assert result.total_rows == 4


def _fmt_record(
    type_id: int,
    name: bytes,
    format_codes: bytes,
    columns: bytes,
    record_length: int,
) -> bytes:
    payload = struct.pack(
        "<BB4s16s64s",
        type_id,
        record_length,
        name.ljust(4, b"\0"),
        format_codes.ljust(16, b"\0"),
        columns.ljust(64, b"\0"),
    )
    return b"\xA3\x95\x80" + payload


def test_fast_log_parser_decodes_raw_dataflash_bin_to_arrow(tmp_path):
    fmt = _fmt_record(1, b"ATT", b"Qff", b"TimeUS,Roll,Pitch", 19)
    att = b"\xA3\x95\x01" + struct.pack("<Qff", 123456, 1.5, -2.0)
    path = tmp_path / "raw.bin"
    path.write_bytes(fmt + att)

    result = FastLogParser(path).parse(("FMT", "ATT"))

    assert result.available_messages == ("ATT", "FMT")
    assert result.format_fields["ATT"] == ("TimeUS", "Roll", "Pitch")
    assert result.formats["ATT"].record_length == len(att)
    assert result.table("FMT").to_pylist()[0]["Name"] == "ATT"
    assert result.table("ATT").to_pylist() == [
        {"TimeUS": 123456, "Roll": 1.5, "Pitch": -2.0}
    ]
    assert result.metadata["memory_mapped"] is True
    assert result.metadata["zero_copy"] == "partial"
    assert "ATT.TimeUS" in result.metadata["zero_copy_fields"]
    source_buffer = result.zero_copy_buffers["ATT.TimeUS"][0]
    arrow_buffer = result.table("ATT").column("TimeUS").chunk(0).buffers()[1]
    assert arrow_buffer.address == pa.py_buffer(source_buffer).address
    assert "mmap-backed Arrow buffers" in result.metadata["copy_boundary"]

    fixed_only = FastLogParser(path).parse("ATT")
    assert fixed_only.metadata["zero_copy"] is True


def test_fast_log_parser_rejects_truncated_typed_record(tmp_path):
    fmt = _fmt_record(1, b"ATT", b"Qff", b"TimeUS,Roll,Pitch", 19)
    att = b"\xA3\x95\x01" + struct.pack("<Qff", 123456, 1.5, -2.0)
    path = tmp_path / "truncated.bin"
    path.write_bytes(fmt + att[:-1])

    with pytest.raises(TruncatedDataFlash):
        FastLogParser(path).parse("ATT")


def test_fast_log_parser_rejects_duplicate_and_unsupported_fmt(tmp_path):
    duplicate = tmp_path / "duplicate.bin"
    fmt = _fmt_record(1, b"ATT", b"Qff", b"TimeUS,Roll,Pitch", 19)
    duplicate.write_bytes(fmt + fmt)
    with pytest.raises(DuplicateDataFlashFormat):
        FastLogParser(duplicate).parse("ATT")

    unsupported = tmp_path / "unsupported.bin"
    unsupported.write_bytes(_fmt_record(1, b"ATT", b"?", b"Value", 4))
    with pytest.raises(UnsupportedFormatCode):
        FastLogParser(unsupported).parse("ATT")


def test_fast_log_parser_rejects_unsafe_path():
    with pytest.raises(UnsafeDataFlashPath):
        FastLogParser("unsafe\0.bin")
