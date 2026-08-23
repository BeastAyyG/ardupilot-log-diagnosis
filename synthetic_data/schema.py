"""Exact parameter-inventory contracts for pinned ArduPilot SITL builds."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

SCHEMA_ID = "logdiagnosis.ardupilot-parameter-schema/v1"
PARAMETER_NAME = re.compile(r"^[A-Z][A-Z0-9_]{0,15}$")
FULL_COMMIT = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def canonical_json_bytes(value: object) -> bytes:
    """Serialize receipts deterministically for hashes and signatures."""

    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_commit(value: str) -> str:
    revision = str(value).strip().lower()
    if not FULL_COMMIT.fullmatch(revision):
        raise ValueError(
            "resolved ArduPilot revision must be a full 40-character commit"
        )
    return revision


def validate_sha256(value: str, field: str) -> str:
    normalized = str(value).strip().lower()
    if not SHA256.fullmatch(normalized):
        raise ValueError(f"{field} must be a lowercase SHA256 digest")
    return normalized


def _parse_parameter_line(line: str, line_number: int) -> tuple[str, float] | None:
    body = line.split("#", 1)[0].strip()
    if not body:
        return None
    if "=" in body:
        parts = body.split("=", 1)
    elif "," in body:
        parts = body.split(",", 1)
    else:
        parts = body.split(None, 1)
    if len(parts) != 2:
        raise ValueError(f"parameter inventory line {line_number} is malformed")
    name = parts[0].strip().upper()
    if not PARAMETER_NAME.fullmatch(name):
        raise ValueError(
            f"invalid ArduPilot parameter name on line {line_number}: {name}"
        )
    try:
        value = float(parts[1].strip())
    except ValueError as exc:
        raise ValueError(f"non-numeric parameter value on line {line_number}") from exc
    if not math.isfinite(value):
        raise ValueError(f"non-finite parameter value on line {line_number}")
    return name, value


@dataclass(frozen=True)
class ParameterSchema:
    """A source- and binary-bound snapshot of the live SITL parameter inventory."""

    ardupilot_commit: str
    binary_sha256: str
    parameters: Mapping[str, float]
    inventory_sha256: str
    source_name: str = ""

    def __post_init__(self) -> None:
        validate_commit(self.ardupilot_commit)
        validate_sha256(self.binary_sha256, "binary_sha256")
        validate_sha256(self.inventory_sha256, "inventory_sha256")
        if not self.parameters:
            raise ValueError("parameter inventory must not be empty")
        for name, value in self.parameters.items():
            if not PARAMETER_NAME.fullmatch(str(name)):
                raise ValueError(f"invalid ArduPilot parameter name: {name}")
            if not math.isfinite(float(value)):
                raise ValueError(f"non-finite value for ArduPilot parameter: {name}")

    @property
    def parameter_names(self) -> set[str]:
        return set(self.parameters)

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA_ID,
            "ardupilot_commit": self.ardupilot_commit,
            "binary_sha256": self.binary_sha256,
            "inventory_sha256": self.inventory_sha256,
            "parameter_name_sha256": self.parameter_name_sha256,
            "source_name": self.source_name,
            "parameters": dict(
                sorted((name, float(value)) for name, value in self.parameters.items())
            ),
        }

    @property
    def parameter_name_sha256(self) -> str:
        return sha256_bytes(canonical_json_bytes(sorted(self.parameters)))

    @property
    def digest(self) -> str:
        return sha256_bytes(canonical_json_bytes(self.to_payload()))

    def write(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.to_payload(), indent=2, sort_keys=True) + "\n"
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(destination)
        return destination

    @classmethod
    def from_inventory(
        cls,
        path: str | Path,
        *,
        ardupilot_commit: str,
        binary_sha256: str,
    ) -> "ParameterSchema":
        source = Path(path)
        raw = source.read_bytes()
        parameters: dict[str, float] = {}
        for line_number, line in enumerate(
            raw.decode("utf-8-sig").splitlines(), start=1
        ):
            parsed = _parse_parameter_line(line, line_number)
            if parsed is None:
                continue
            name, value = parsed
            if name in parameters and parameters[name] != value:
                raise ValueError(
                    f"parameter inventory contains conflicting duplicate: {name}"
                )
            parameters[name] = value
        return cls(
            ardupilot_commit=validate_commit(ardupilot_commit),
            binary_sha256=validate_sha256(binary_sha256, "binary_sha256"),
            parameters=parameters,
            inventory_sha256=sha256_bytes(raw),
            source_name=source.name,
        )

    @classmethod
    def read(cls, path: str | Path) -> "ParameterSchema":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if payload.get("schema") != SCHEMA_ID:
            raise ValueError("unsupported parameter schema")
        parameters = payload.get("parameters")
        if not isinstance(parameters, dict):
            raise ValueError("parameter schema lacks a parameter mapping")
        return cls(
            ardupilot_commit=payload.get("ardupilot_commit", ""),
            binary_sha256=payload.get("binary_sha256", ""),
            inventory_sha256=payload.get("inventory_sha256", ""),
            source_name=str(payload.get("source_name", "")),
            parameters={str(name): float(value) for name, value in parameters.items()},
        )
