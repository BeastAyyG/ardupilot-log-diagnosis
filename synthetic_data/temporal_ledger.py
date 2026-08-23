"""Extract a deterministic temporal ledger from dataset-bound raw flight logs."""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.parser.bin_parser import LogParser

from .contracts import validate_contract
from .fidelity_statistics import STRATIFIER_FIELDS
from .schema import sha256_file
from .splits import load_and_validate_ledger
from .temporal_fidelity import LEDGER_SCHEMA, load_temporal_design

ParserFactory = Callable[[str], Any]
SYNTHETIC_TYPES = {"sitl", "hil", "simulation"}


def _resolve_log(logs_root: Path, source_log: str) -> Path:
    raw = Path(source_log)
    candidate = (raw if raw.is_absolute() else logs_root / raw).resolve()
    try:
        candidate.relative_to(logs_root)
    except ValueError as exc:
        raise ValueError("temporal source log escapes the logs root") from exc
    if not candidate.is_file():
        raise ValueError(f"temporal source log is missing: {source_log}")
    return candidate


def _selector_matches(row: dict[str, Any], selector: dict[str, Any]) -> bool:
    for field, expected in selector.items():
        actual = row.get(field)
        if isinstance(expected, (int, float)) and not isinstance(expected, bool):
            if (
                isinstance(actual, bool)
                or not isinstance(actual, (int, float))
                or not math.isclose(float(actual), float(expected), abs_tol=1e-12)
            ):
                return False
        elif str(actual) != str(expected):
            return False
    return True


def _channel_from_messages(
    parsed: dict[str, Any], channel_name: str, source: dict[str, Any]
) -> dict[str, list[Any]]:
    message_type = source["message_type"]
    rows = parsed.get("messages", {}).get(message_type, [])
    if not isinstance(rows, list):
        raise ValueError(f"parsed message stream {message_type} is malformed")
    time_field = source["time_field"]
    value_field = source["value_field"]
    time_scale = float(source["time_scale_to_sec"])
    value_scale = float(source["value_scale"])
    value_offset = float(source["value_offset"])
    selector = source["selector"]
    by_time: dict[float, list[float | None]] = {}
    for row in rows:
        if not isinstance(row, dict) or not _selector_matches(row, selector):
            continue
        raw_time = row.get(time_field)
        if (
            isinstance(raw_time, bool)
            or not isinstance(raw_time, (int, float))
            or not math.isfinite(float(raw_time))
        ):
            continue
        timestamp = float(raw_time) * time_scale
        raw_value = row.get(value_field)
        value: float | None = None
        if (
            not isinstance(raw_value, bool)
            and isinstance(raw_value, (int, float))
            and math.isfinite(float(raw_value))
        ):
            value = float(raw_value) * value_scale + value_offset
        by_time.setdefault(timestamp, []).append(value)
    times = sorted(by_time)
    values: list[float | None] = []
    for timestamp in times:
        finite = [value for value in by_time[timestamp] if value is not None]
        values.append(float(np.median(finite)) if finite else None)
    if len(times) < 16:
        raise ValueError(
            f"raw log has fewer than 16 usable {channel_name}/{message_type} samples"
        )
    return {"time_sec": times, "values": values}


def _matches_required_stratum(
    row: pd.Series, domain: str, required: list[dict[str, Any]]
) -> bool:
    row_key = tuple(str(row.get(name, "")).strip() for name in STRATIFIER_FIELDS)
    for entry in required:
        key = tuple(str(entry[name]).strip() for name in STRATIFIER_FIELDS)
        if (domain == "real" and row_key[:-1] == key[:-1]) or (
            domain == "synthetic" and row_key == key
        ):
            return True
    return False


def build_temporal_ledger(
    design_path: str | Path,
    logs_root: str | Path,
    *,
    features_csv: str | Path,
    labels_csv: str | Path,
    groups_csv: str | Path,
    split_ledger_path: str | Path,
    output_path: str | Path | None = None,
    parser_factory: ParserFactory = LogParser,
) -> dict[str, Any]:
    """Extract only preregistered real-train and accepted-synthetic lineages."""

    design = load_temporal_design(design_path)
    root = Path(logs_root).resolve()
    if not root.is_dir():
        raise ValueError("temporal logs root is not a directory")
    groups = pd.read_csv(groups_csv).fillna("")
    required_columns = {
        "source_log",
        "source_group",
        "lineage_root_id",
        "primary_label",
        "source_type",
        "verification_status",
        "sha256",
        "near_duplicate_cluster_id",
        "fault_onset_sec",
        *STRATIFIER_FIELDS,
    }
    missing = sorted(required_columns - set(groups.columns))
    if missing:
        raise ValueError("temporal ledger groups lack " + ", ".join(missing))
    split = load_and_validate_ledger(
        split_ledger_path,
        labels_csv,
        groups_csv,
    )
    assignments = split["source_group_assignments"]
    selected: dict[tuple[str, str, tuple[str, ...]], pd.Series] = {}
    for _, row in groups.iterrows():
        source_type = str(row["source_type"]).strip()
        domain = (
            "real"
            if source_type == "real"
            else ("synthetic" if source_type in SYNTHETIC_TYPES else "")
        )
        if not domain:
            continue
        if (
            domain == "real"
            and assignments.get(str(row["source_group"])) != "real_train"
        ):
            continue
        if (
            domain == "synthetic"
            and str(row["verification_status"]).strip() != "accepted"
        ):
            continue
        if not _matches_required_stratum(row, domain, design["required_strata"]):
            continue
        key = (
            domain,
            str(row["lineage_root_id"]).strip(),
            tuple(str(row[name]).strip() for name in STRATIFIER_FIELDS),
        )
        previous = selected.get(key)
        if previous is not None and (
            str(previous["source_log"]) != str(row["source_log"])
            or str(previous["sha256"]) != str(row["sha256"])
        ):
            raise ValueError("one temporal lineage-stratum maps to multiple raw logs")
        selected[key] = row
    if not selected:
        raise ValueError("no dataset rows match the temporal fidelity design")

    records: list[dict[str, Any]] = []
    parsed_cache: dict[Path, dict[str, Any]] = {}
    for (domain, lineage, stratum_key), row in sorted(selected.items()):
        path = _resolve_log(root, str(row["source_log"]))
        if sha256_file(path) != str(row["sha256"]).strip():
            raise ValueError("temporal raw log hash differs from groups provenance")
        if path not in parsed_cache:
            parsed = parser_factory(str(path)).parse()
            metadata = parsed.get("metadata", {})
            if metadata.get("parse_complete") is not True or metadata.get(
                "parse_error"
            ):
                raise ValueError(
                    f"temporal raw log did not parse completely: {path.name}"
                )
            parsed_cache[path] = parsed
        parsed = parsed_cache[path]
        channels = {
            name: _channel_from_messages(
                parsed,
                name,
                design["channel_sources"][name],
            )
            for name in design["required_channels"]
        }
        raw_transition = row["fault_onset_sec"]
        transition: float | None = None
        if str(raw_transition).strip():
            transition = float(raw_transition)
            if not math.isfinite(transition):
                raise ValueError("temporal transition timing is non-finite")
        if design["require_transition_timing"] and transition is None:
            raise ValueError(
                "temporal design requires fault_onset_sec for every record"
            )
        records.append(
            {
                "domain": domain,
                "lineage_root_id": lineage,
                "near_duplicate_cluster_id": str(
                    row["near_duplicate_cluster_id"]
                ).strip(),
                "source_artifact_sha256": str(row["sha256"]).strip(),
                "stratum": {
                    name: value for name, value in zip(STRATIFIER_FIELDS, stratum_key)
                },
                "transition_time_sec": transition,
                "channels": channels,
            }
        )
    ledger = {
        "schema": LEDGER_SCHEMA,
        "candidate_manifest_sha256": design["candidate_manifest_sha256"],
        "temporal_design_sha256": sha256_file(design_path),
        "dataset": {
            "features_sha256": sha256_file(features_csv),
            "labels_sha256": sha256_file(labels_csv),
            "groups_sha256": sha256_file(groups_csv),
            "split_ledger_sha256": sha256_file(split_ledger_path),
        },
        "records": records,
    }
    validate_contract(ledger, "temporal_fidelity_ledger.schema.json")
    if output_path is not None:
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(ledger, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
    return ledger
