"""Two-pass memory-mapped Arrow telemetry extraction.

The parser consumes an Arrow IPC file produced by a DataFlash conversion step.
It reflects the schema and message-name column at runtime; message positions
are never assumed.  Record batches are scanned twice, so the first pass only
discovers available message families and the second pass materializes the
requested tables.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pyarrow as pa

DEFAULT_MESSAGES = ("ATT", "VIBE", "RCOU", "BAT", "IMU", "GPS", "POS", "ERR")
_MESSAGE_FIELD_NAMES = {
    "message",
    "message_name",
    "message_type",
    "msg",
    "msgname",
    "type",
}


@dataclass(frozen=True, slots=True)
class ArrowTelemetryResult:
    """Selected telemetry tables plus schema-discovery metadata."""

    tables: Mapping[str, pa.Table]
    available_messages: tuple[str, ...]
    format_fields: Mapping[str, tuple[str, ...]]
    record_batches: int
    total_rows: int
    requested_messages: tuple[str, ...] = DEFAULT_MESSAGES

    @property
    def missing_messages(self) -> tuple[str, ...]:
        """Return requested families that were absent from the result."""

        return tuple(name for name in self.requested_messages if name not in self.tables)

    def table(self, message_name: str) -> pa.Table | None:
        """Return a selected table by message family."""

        return self.tables.get(message_name.upper())


def _validate_path(path: str | Path) -> Path:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(file_path)
    if not file_path.is_file():
        raise ValueError(f"Arrow input must be a regular file: {file_path}")
    if file_path.stat().st_size == 0:
        raise ValueError(f"Arrow input is empty: {file_path}")
    return file_path


def _message_field(schema: pa.Schema) -> str | None:
    for field in schema:
        if field.name.lower() in _MESSAGE_FIELD_NAMES:
            return field.name
    return None


def _metadata_message(schema: pa.Schema) -> str | None:
    metadata = schema.metadata or {}
    for key in (b"message_type", b"message", b"msg_type"):
        value = metadata.get(key)
        if value:
            return value.decode("utf-8").strip().upper()
    return None


def _string_column(batch: pa.RecordBatch, name: str) -> pa.Array:
    import pyarrow as pa
    from pyarrow import compute as pc

    column = batch.column(name)
    if pa.types.is_string(column.type) or pa.types.is_large_string(column.type):
        return column
    return pc.cast(column, pa.string())


def _fmt_fields(table: pa.Table | None) -> dict[str, tuple[str, ...]]:
    if table is None:
        return {}
    names = {name.lower(): name for name in table.column_names}
    message_name = next(
        (names[name] for name in ("name", "msgname", "message_name", "type") if name in names),
        None,
    )
    columns_name = next(
        (names[name] for name in ("columns", "fields", "format", "field_names") if name in names),
        None,
    )
    if not message_name or not columns_name:
        return {"FMT": tuple(table.column_names)}
    result: dict[str, tuple[str, ...]] = {}
    for row in table.select([message_name, columns_name]).to_pylist():
        msg = str(row.get(message_name, "")).strip().upper()
        raw_fields = row.get(columns_name)
        if not msg or raw_fields is None:
            continue
        fields = tuple(
            field.strip()
            for field in (raw_fields if isinstance(raw_fields, list) else str(raw_fields).split(","))
            if field.strip()
        )
        result[msg] = fields
    return result


def parse_arrow(
    path: str | Path,
    requested_messages: Sequence[str] | str = DEFAULT_MESSAGES,
) -> ArrowTelemetryResult:
    """Extract requested message families from a memory-mapped Arrow IPC file."""

    raw_requested = (requested_messages,) if isinstance(requested_messages, str) else requested_messages
    try:
        requested_names = tuple(raw_requested)
    except TypeError as exc:
        raise TypeError("requested_messages must be a string or sequence of strings") from exc
    normalized_names: list[str] = []
    for name in requested_names:
        if not isinstance(name, str):
            raise TypeError("requested_messages must contain only strings")
        normalized = name.strip().upper()
        if normalized:
            normalized_names.append(normalized)
    requested = tuple(dict.fromkeys(normalized_names))
    if not requested:
        raise ValueError("requested_messages must contain at least one name")
    file_path = _validate_path(path)
    import pyarrow as pa
    from pyarrow import compute as pc
    from pyarrow import ipc

    source = pa.memory_map(str(file_path), "r")
    try:
        try:
            reader = ipc.open_file(source)
        except (pa.ArrowInvalid, OSError) as exc:
            raise ValueError("input is not an Arrow IPC file written with random-access batches") from exc

        schema = reader.schema
        message_field = _message_field(schema)
        record_batches = reader.num_record_batches
        available: set[str] = set()
        batch_metadata: list[str | None] = []
        total_rows = 0

        # Pass one: discover the message families and batch metadata only.
        for index in range(record_batches):
            batch = reader.get_batch(index)
            total_rows += batch.num_rows
            metadata_name = _metadata_message(batch.schema)
            batch_metadata.append(metadata_name)
            if message_field:
                values = _string_column(batch, message_field)
                available.update(str(value).strip().upper() for value in pc.unique(values).to_pylist() if value is not None)
            elif metadata_name:
                available.add(metadata_name)

        batches_by_message: dict[str, list[pa.RecordBatch]] = {name: [] for name in requested}
        # Pass two: filter each batch by the reflected message-name field.
        for index in range(record_batches):
            batch = reader.get_batch(index)
            metadata_name = batch_metadata[index]
            if message_field:
                names = _string_column(batch, message_field)
                for name in requested:
                    mask = pc.equal(names, pa.scalar(name))
                    selected = batch.filter(mask)
                    if selected.num_rows:
                        batches_by_message[name].append(selected)
            elif metadata_name in batches_by_message:
                batches_by_message[metadata_name].append(batch)

        tables = {
            name: pa.Table.from_batches(batches)
            for name, batches in batches_by_message.items()
            if batches
        }
        fmt_table = tables.get("FMT")
        return ArrowTelemetryResult(
            tables=tables,
            available_messages=tuple(sorted(available)),
            format_fields=_fmt_fields(fmt_table),
            record_batches=record_batches,
            total_rows=total_rows,
            requested_messages=requested,
        )
    finally:
        source.close()
