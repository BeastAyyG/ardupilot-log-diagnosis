"""Read raw ArduPilot DataFlash bytes into deterministic Arrow tables."""

from __future__ import annotations

import mmap
import os
import struct
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_MESSAGES = ("ATT", "VIBE", "RCOU", "BAT", "IMU", "GPS", "POS", "ERR")
_HEADER = b"\xA3\x95"
_FMT_TYPE = 0x80
_FMT_STRUCT = struct.Struct("<BB4s16s64s")
_FORMAT_TO_STRUCT: dict[str, tuple[str, float | None]] = {
    "a": ("64s", None),
    "b": ("b", None),
    "B": ("B", None),
    "g": ("e", None),
    "h": ("h", None),
    "H": ("H", None),
    "i": ("i", None),
    "I": ("I", None),
    "f": ("f", None),
    "n": ("4s", None),
    "N": ("16s", None),
    "Z": ("64s", None),
    "c": ("h", 0.01),
    "C": ("H", 0.01),
    "e": ("i", 0.01),
    "E": ("I", 0.01),
    "L": ("i", 1.0e-7),
    "d": ("d", None),
    "M": ("b", None),
    "q": ("q", None),
    "Q": ("Q", None),
}


class DataFlashError(ValueError):
    """Base class for explicit raw DataFlash boundary failures."""


class UnsafeDataFlashPath(DataFlashError):
    """The supplied path is not a safe regular-file input."""


class InvalidDataFlash(DataFlashError):
    """The input is not a valid DataFlash byte stream."""


class UnsupportedFormatCode(DataFlashError):
    """An FMT record declares a format code this adapter cannot decode."""


class TruncatedDataFlash(DataFlashError):
    """A header, FMT record, or typed record ends before the file boundary."""


class DuplicateDataFlashFormat(DataFlashError):
    """A message type or name is declared by more than one FMT record."""


@dataclass(frozen=True, slots=True)
class DataFlashFormat:
    """One validated DataFlash FMT descriptor."""

    type_id: int
    name: str
    record_length: int
    format_codes: str
    columns: tuple[str, ...]
    payload_size: int
    struct_format: str
    field_offsets: tuple[int, ...]
    field_sizes: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class DataFlashArrowResult:
    """Arrow tables and the evidence needed to interpret their memory boundary."""

    tables: Mapping[str, Any]
    available_messages: tuple[str, ...]
    format_fields: Mapping[str, tuple[str, ...]]
    formats: Mapping[str, DataFlashFormat]
    record_count: int
    total_rows: int
    metadata: Mapping[str, object]
    requested_messages: tuple[str, ...] = DEFAULT_MESSAGES
    zero_copy_buffers: Mapping[str, tuple[memoryview, ...]] = field(
        default_factory=dict, repr=False, compare=False
    )
    _mapped: mmap.mmap | None = field(default=None, repr=False, compare=False)

    @property
    def missing_messages(self) -> tuple[str, ...]:
        return tuple(name for name in self.requested_messages if name not in self.tables)

    def table(self, message_name: str) -> Any | None:
        """Return a selected message table by case-insensitive name."""

        return self.tables.get(message_name.strip().upper())


ArrowTelemetryResult = DataFlashArrowResult


def _requested_messages(requested_messages: Sequence[str] | str) -> tuple[str, ...]:
    raw = (requested_messages,) if isinstance(requested_messages, str) else requested_messages
    try:
        names = tuple(raw)
    except TypeError as exc:
        raise TypeError("requested_messages must be a string or sequence of strings") from exc
    normalized: list[str] = []
    for name in names:
        if not isinstance(name, str):
            raise TypeError("requested_messages must contain only strings")
        value = name.strip().upper()
        if value:
            normalized.append(value)
    result = tuple(dict.fromkeys(normalized))
    if not result:
        raise ValueError("requested_messages must contain at least one name")
    return result


def _safe_path(path: str | Path) -> Path:
    try:
        raw = os.fspath(path)
    except TypeError as exc:
        raise TypeError("path must be a string or pathlib.Path") from exc
    if isinstance(raw, bytes) or "\x00" in raw:
        raise UnsafeDataFlashPath("DataFlash path must not contain NUL bytes")
    file_path = Path(raw)
    if file_path.is_symlink():
        raise UnsafeDataFlashPath(f"DataFlash path must not be a symbolic link: {file_path}")
    if not file_path.exists():
        raise FileNotFoundError(file_path)
    if not file_path.is_file():
        raise UnsafeDataFlashPath(f"DataFlash input must be a regular file: {file_path}")
    if file_path.stat().st_size < len(_HEADER) + 1:
        raise InvalidDataFlash("DataFlash input is too short to contain a record header")
    return file_path


def _text(raw: bytes) -> str:
    return raw.split(b"\0", 1)[0].decode("utf-8", errors="backslashreplace").strip()


def _compile_format(
    type_id: int,
    name: str,
    record_length: int,
    format_codes: str,
    columns: tuple[str, ...],
) -> DataFlashFormat:
    if not name:
        raise InvalidDataFlash("FMT record has an empty message name")
    if not format_codes:
        raise InvalidDataFlash(f"FMT record {name} has an empty format")
    if len(columns) != len(format_codes):
        raise InvalidDataFlash(
            f"FMT record {name} declares {len(format_codes)} codes and {len(columns)} columns"
        )
    if len(set(columns)) != len(columns):
        raise InvalidDataFlash(f"FMT record {name} declares duplicate columns")
    struct_parts: list[str] = []
    field_offsets: list[int] = []
    field_sizes: list[int] = []
    payload_offset = 0
    for code in format_codes:
        try:
            struct_code, _ = _FORMAT_TO_STRUCT[code]
        except KeyError as exc:
            raise UnsupportedFormatCode(
                f"FMT record {name} declares unsupported format code {code!r}"
            ) from exc
        size = struct.calcsize("<" + struct_code)
        field_offsets.append(payload_offset)
        field_sizes.append(size)
        payload_offset += size
        struct_parts.append(struct_code)
    struct_format = "<" + "".join(struct_parts)
    try:
        payload_size = struct.calcsize(struct_format)
    except struct.error as exc:
        raise InvalidDataFlash(f"FMT record {name} has an invalid layout") from exc
    expected_length = 3 + payload_size
    if record_length != expected_length:
        raise InvalidDataFlash(
            f"FMT record {name} length {record_length} does not match {expected_length}"
        )
    return DataFlashFormat(
        type_id=type_id,
        name=name.upper(),
        record_length=record_length,
        format_codes=format_codes,
        columns=columns,
        payload_size=payload_size,
        struct_format=struct_format,
        field_offsets=tuple(field_offsets),
        field_sizes=tuple(field_sizes),
    )


def _builtin_format() -> DataFlashFormat:
    return _compile_format(
        _FMT_TYPE,
        "FMT",
        3 + _FMT_STRUCT.size,
        "BBnNZ",
        ("Type", "Length", "Name", "Format", "Columns"),
    )


def _parse_fmt(view: memoryview, offset: int) -> tuple[DataFlashFormat, dict[str, object]]:
    if len(view) - offset < 3 + _FMT_STRUCT.size:
        raise TruncatedDataFlash(f"truncated FMT record at byte offset {offset}")
    type_id, data_record_length, name_raw, format_raw, columns_raw = _FMT_STRUCT.unpack(
        view[offset + 3 : offset + 3 + _FMT_STRUCT.size]
    )
    name = _text(name_raw).upper()
    format_codes = _text(format_raw)
    columns = tuple(part.strip() for part in _text(columns_raw).split(",") if part.strip())
    descriptor = _compile_format(
        type_id, name, data_record_length, format_codes, columns
    )
    return descriptor, {
        "Type": type_id,
        "Length": data_record_length,
        "Name": name,
        "Format": format_codes,
        "Columns": ",".join(columns),
    }


def _decode_value(value: object, code: str, scale: float | None) -> object:
    if code in "anNZ" and isinstance(value, bytes):
        return _text(value)
    if scale is not None:
        return float(value) * scale
    return value


def _decode_record(descriptor: DataFlashFormat, payload: memoryview) -> dict[str, object]:
    try:
        values = struct.unpack(descriptor.struct_format, payload)
    except struct.error as exc:
        raise TruncatedDataFlash(f"truncated {descriptor.name} record") from exc
    return {
        column: _decode_value(value, code, _FORMAT_TO_STRUCT[code][1])
        for column, code, value in zip(descriptor.columns, descriptor.format_codes, values)
    }


def _arrow_type(code: str, pa: Any) -> Any | None:
    return {
        "b": pa.int8,
        "B": pa.uint8,
        "g": pa.float16,
        "h": pa.int16,
        "H": pa.uint16,
        "i": pa.int32,
        "I": pa.uint32,
        "f": pa.float32,
        "d": pa.float64,
        "M": pa.int8,
        "q": pa.int64,
        "Q": pa.uint64,
    }.get(code)


def _arrow_table(rows: list[dict[str, object]], columns: tuple[str, ...], pa: Any) -> Any:
    return pa.Table.from_pydict({column: [row[column] for row in rows] for column in columns})


def _telemetry_table(
    descriptor: DataFlashFormat,
    rows: list[dict[str, object]],
    offsets: list[int],
    source: memoryview,
    pa: Any,
) -> tuple[Any, dict[str, tuple[memoryview, ...]], set[str]]:
    columns: dict[str, Any] = {}
    zero_copy_buffers: dict[str, tuple[memoryview, ...]] = {}
    copied_fields: set[str] = set()
    for index, (column, code) in enumerate(zip(descriptor.columns, descriptor.format_codes)):
        arrow_factory = _arrow_type(code, pa) if _FORMAT_TO_STRUCT[code][1] is None else None
        if arrow_factory is not None:
            arrow_type = arrow_factory()
            chunks: list[Any] = []
            buffers: list[memoryview] = []
            for record_offset in offsets:
                start = record_offset + 3 + descriptor.field_offsets[index]
                raw_field = source[start : start + descriptor.field_sizes[index]]
                chunks.append(
                    pa.Array.from_buffers(
                        arrow_type, 1, [None, pa.py_buffer(raw_field)]
                    )
                )
                buffers.append(raw_field)
            columns[column] = pa.chunked_array(chunks, type=arrow_type)
            zero_copy_buffers[f"{descriptor.name}.{column}"] = tuple(buffers)
        else:
            columns[column] = pa.array([row[column] for row in rows])
            copied_fields.add(f"{descriptor.name}.{column}")
    return pa.Table.from_pydict(columns), zero_copy_buffers, copied_fields


def _parse_mapped(
    mapped: mmap.mmap,
    requested: tuple[str, ...],
    pa: Any,
) -> DataFlashArrowResult:
    view = memoryview(mapped)
    try:
        if view[:2].tobytes() != _HEADER:
            raise InvalidDataFlash("DataFlash input must begin with signature a3 95")
        builtin = _builtin_format()
        formats_by_id: dict[int, DataFlashFormat] = {_FMT_TYPE: builtin}
        formats_by_name: dict[str, DataFlashFormat] = {"FMT": builtin}
        seen_fmt_record = False
        rows_by_name: dict[str, list[dict[str, object]]] = {}
        offsets_by_name: dict[str, list[int]] = {}
        offset = 0
        record_count = 0
        fmt_count = 0
        while offset < len(view):
            if len(view) - offset < 3:
                raise TruncatedDataFlash(f"truncated record header at byte offset {offset}")
            if view[offset : offset + 2].tobytes() != _HEADER:
                raise InvalidDataFlash(f"invalid record header at byte offset {offset}")
            message_type = int(view[offset + 2])
            if message_type == _FMT_TYPE:
                descriptor, fmt_row = _parse_fmt(view, offset)
                if descriptor.type_id == _FMT_TYPE:
                    raise DuplicateDataFlashFormat("type 128 is reserved for FMT")
                if descriptor.type_id in formats_by_id:
                    raise DuplicateDataFlashFormat(
                        f"duplicate FMT type id {descriptor.type_id}"
                    )
                if descriptor.name in formats_by_name:
                    raise DuplicateDataFlashFormat(f"duplicate FMT name {descriptor.name}")
                formats_by_id[descriptor.type_id] = descriptor
                formats_by_name[descriptor.name] = descriptor
                rows_by_name.setdefault("FMT", []).append(fmt_row)
                fmt_count += 1
                seen_fmt_record = True
                offset += 3 + _FMT_STRUCT.size
                record_count += 1
                continue

            descriptor = formats_by_id.get(message_type)
            if descriptor is None:
                raise InvalidDataFlash(
                    f"message type {message_type} has no preceding FMT descriptor"
                )
            end = offset + descriptor.record_length
            if end > len(view):
                raise TruncatedDataFlash(
                    f"truncated {descriptor.name} record at byte offset {offset}"
                )
            row = _decode_record(descriptor, view[offset + 3 : end])
            rows_by_name.setdefault(descriptor.name, []).append(row)
            offsets_by_name.setdefault(descriptor.name, []).append(offset)
            offset = end
            record_count += 1

        if not seen_fmt_record:
            raise InvalidDataFlash("DataFlash input contains no FMT descriptor")
        tables: dict[str, Any] = {}
        zero_copy_buffers: dict[str, tuple[memoryview, ...]] = {}
        copied_fields: set[str] = set()
        for name in requested:
            if name not in rows_by_name or name not in formats_by_name:
                continue
            if name == "FMT":
                tables[name] = _arrow_table(rows_by_name[name], builtin.columns, pa)
                copied_fields.update(f"FMT.{column}" for column in builtin.columns)
                continue
            table, buffers, copied = _telemetry_table(
                formats_by_name[name],
                rows_by_name[name],
                offsets_by_name[name],
                view,
                pa,
            )
            tables[name] = table
            zero_copy_buffers.update(buffers)
            copied_fields.update(copied)
        all_formats = {name: formats_by_name[name] for name in sorted(formats_by_name)}
        zero_copy_fields = tuple(sorted(zero_copy_buffers))
        zero_copy_status: object = (
            True
            if zero_copy_fields and not copied_fields
            else "partial"
            if zero_copy_fields
            else False
        )
        return DataFlashArrowResult(
            tables=tables,
            available_messages=tuple(sorted(rows_by_name)),
            format_fields={name: fmt.columns for name, fmt in all_formats.items()},
            formats=all_formats,
            record_count=record_count,
            total_rows=sum(len(rows) for rows in rows_by_name.values()),
            metadata={
                "source_format": "ArduPilot DataFlash BIN",
                "signature": _HEADER.hex(),
                "memory_mapped": True,
                "zero_copy": zero_copy_status,
                "zero_copy_fields": zero_copy_fields,
                "copied_fields": tuple(sorted(copied_fields)),
                "copy_boundary": (
                    "fixed-width unscaled fields use mmap-backed Arrow buffers; "
                    "scaled and text fields decode through Python values"
                ),
                "decoded_records": record_count,
                "fmt_records": fmt_count,
            },
            requested_messages=requested,
            zero_copy_buffers=zero_copy_buffers,
            _mapped=mapped,
        )
    finally:
        view.release()


class FastLogParser:
    """Parse a raw DataFlash BIN using its on-disk FMT declarations."""

    def __init__(self, path: str | Path):
        self.path = _safe_path(path)

    def parse(
        self,
        requested_messages: Sequence[str] | str = DEFAULT_MESSAGES,
    ) -> DataFlashArrowResult:
        requested = _requested_messages(requested_messages)
        try:
            import pyarrow as pa
        except ImportError as exc:
            raise RuntimeError("pyarrow is required for raw DataFlash Arrow extraction") from exc
        handle = self.path.open("rb")
        mapped: mmap.mmap | None = None
        try:
            mapped = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
            return _parse_mapped(mapped, requested, pa)
        except Exception:
            if mapped is not None:
                try:
                    mapped.close()
                except BufferError:
                    mapped = None
            raise
        finally:
            handle.close()


__all__ = [
    "DEFAULT_MESSAGES",
    "ArrowTelemetryResult",
    "DataFlashArrowResult",
    "DataFlashError",
    "DataFlashFormat",
    "DuplicateDataFlashFormat",
    "FastLogParser",
    "InvalidDataFlash",
    "TruncatedDataFlash",
    "UnsafeDataFlashPath",
    "UnsupportedFormatCode",
]
