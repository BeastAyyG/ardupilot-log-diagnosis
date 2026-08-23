"""Source-bound extraction and window-provenance helpers."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

GROUP_COLUMNS = [
    "source_log",
    "source_group",
    "lineage_root_id",
    "source_url",
    "primary_label",
    "sha256",
    "source_type",
    "physical_flight_verified",
    "label_origin",
    "verification_status",
    "manifest_sha256",
    "parameter_schema_sha256",
    "artifact_sha256",
    "run_fingerprint",
    "simulation_family",
    "scenario_sampling_seed",
    "generator_version",
    "conditioning_mode",
    "conditioning_real_lineage_id",
    "near_duplicate_cluster_id",
    "vehicle_frame",
    "firmware_commit",
    "flight_phase",
    "scenario",
    "pair_role",
    "run_id",
    "paired_with",
    "manifestation_predicate_sha256",
    "fault_onset_sec",
    "window_start_sec",
    "window_end_sec",
    "window_phase",
]


def safe_dataset_file(dataset_root: Path, filename: object) -> Path:
    name = str(filename or "")
    candidate = Path(name)
    if not name or candidate.is_absolute() or candidate.name != name:
        raise ValueError(f"unsafe ground-truth filename: {name}")
    root = dataset_root.resolve()
    resolved = (root / candidate).resolve()
    if resolved.parent != root:
        raise ValueError(f"ground-truth filename escapes dataset directory: {name}")
    return resolved


def explicit_bool(value: object) -> bool:
    return value is True or str(value).strip().lower() in {"1", "true", "yes"}


def verified_synthetic_attestation(entry: Mapping[str, object]) -> bool:
    fields = (
        "manifest_sha256",
        "parameter_schema_sha256",
        "run_fingerprint",
        "manifestation_predicate_sha256",
    )
    return all(
        SHA256_PATTERN.fullmatch(str(entry.get(field, "") or "").strip().lower())
        for field in fields
    )


def schema_hash(values: list[str]) -> str:
    payload = json.dumps(values, sort_keys=False, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def extractor_source_hash() -> str:
    digest = hashlib.sha256()
    paths = sorted((ROOT_DIR / "src" / "features").rglob("*.py"))
    paths.extend(
        [
            ROOT_DIR / "src" / "analysis" / "windowing.py",
            ROOT_DIR / "src" / "constants.py",
            ROOT_DIR / "src" / "parser" / "bin_parser.py",
            ROOT_DIR / "src" / "parser" / "file_format.py",
            ROOT_DIR / "training" / "build_dataset.py",
            ROOT_DIR / "training" / "dataset_build_contract.py",
            ROOT_DIR / "training" / "window_slicer.py",
        ]
    )
    for path in paths:
        digest.update(path.relative_to(ROOT_DIR).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def finite_onset(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        onset = float(value)
    except (TypeError, ValueError):
        return None
    return onset if math.isfinite(onset) and onset >= 0 else None


def window_phase(
    log_slice: dict,
    *,
    synthetic_fault: bool,
    onset_sec: float | None,
    guard_sec: float,
) -> tuple[str, float | None, float | None]:
    metadata = log_slice.get("metadata", {})
    start = metadata.get("window_start")
    end = metadata.get("window_end")
    try:
        start_value = float(start)
        end_value = float(end)
    except (TypeError, ValueError):
        start_value = end_value = None
    if not synthetic_fault:
        phase = "window" if start_value is not None else "full_log"
        return phase, start_value, end_value
    if onset_sec is None:
        return "invalid_onset", start_value, end_value
    if start_value is None or end_value is None:
        return "mixed_full_log", start_value, end_value
    if end_value <= onset_sec - guard_sec:
        return "pre_fault", start_value, end_value
    if start_value < onset_sec + guard_sec:
        return "transition", start_value, end_value
    return "post_fault", start_value, end_value
