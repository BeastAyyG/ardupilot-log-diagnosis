"""Shared contracts for provenance and label handling in training data.

The model is evaluated at the source-incident level, not at the individual
window level.  This module keeps that contract in one place so dataset
building, training, calibration, and artifact validation cannot silently use
different grouping or primary-label semantics.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import numpy as np
import pandas as pd


REAL_SOURCE_TYPES = frozenset({"real"})
SYNTHETIC_SOURCE_TYPES = frozenset(
    {"sitl", "hil", "feature_synthetic", "simulation"}
)
KNOWN_SOURCE_TYPES = REAL_SOURCE_TYPES | SYNTHETIC_SOURCE_TYPES | {"unknown"}
_REAL_ALIASES = frozenset(
    {
        "real",
        "hardware",
        "real_flight",
        "release_benchmark",
        "flight_log",
        "expert_verified",
        "expert_curated",
        "ardupilot_discuss",
        "ardupilot_forum",
        "community_log",
        "forum_linked",
        "github",
        "github_real_log",
        "human_verified_rule_candidate",
        "local_real_log",
    }
)
_BASIC_SIMULATION_ALIASES = frozenset(
    {"basic", "basic_dataset", "basic_sitl_dataset", "basic_simulation_dataset"}
)


def canonical_source_type(
    value: object,
    *,
    source_group: object = "",
    source_log: object = "",
) -> str:
    """Normalize provenance into a small set used by evaluation policy.

    Older datasets did not carry a ``source_type`` column.  They remain
    readable, but synthetic/SITL prefixes are still detected so those rows
    cannot silently enter a real-world holdout.
    """

    try:
        missing = value is None or bool(pd.isna(value))
    except (TypeError, ValueError):
        missing = value is None
    raw = (
        ""
        if missing
        else str(value).strip().lower().replace("-", "_").replace(" ", "_")
    )
    marker = f"{source_group or ''} {source_log or ''}".strip().lower()
    if raw in _REAL_ALIASES:
        return "real"
    if raw in _BASIC_SIMULATION_ALIASES or raw.startswith("basic_dataset"):
        return "simulation"
    if "feature_synthetic" in raw or raw in {"synthetic", "generated_features"}:
        return "feature_synthetic"
    if "sitl" in raw or "software_in_the_loop" in raw:
        return "sitl"
    if raw == "hil" or "hardware_in_the_loop" in raw or raw.startswith("hil_"):
        return "hil"
    if raw in {"simulation", "simulated"}:
        return "simulation"
    if marker.startswith("synthetic:") or " synthetic:" in marker:
        return "feature_synthetic"
    if marker.startswith("sitl:") or " sitl:" in marker:
        return "sitl"
    if marker.startswith("hil:") or " hil:" in marker:
        return "hil"
    return "unknown"


def effective_source_types(groups: pd.DataFrame) -> np.ndarray:
    """Return one normalized provenance type for every dataset row."""

    values = groups["source_type"] if "source_type" in groups.columns else [""] * len(groups)
    source_groups = (
        groups["source_group"] if "source_group" in groups.columns else [""] * len(groups)
    )
    source_logs = groups["source_log"] if "source_log" in groups.columns else [""] * len(groups)
    return np.asarray(
        [
            canonical_source_type(value, source_group=group, source_log=log)
            for value, group, log in zip(values, source_groups, source_logs)
        ]
    )


def synthetic_source_mask(groups: pd.DataFrame) -> np.ndarray:
    """Identify rows that may train a model but may never score release metrics."""

    return np.isin(effective_source_types(groups), tuple(SYNTHETIC_SOURCE_TYPES))


def real_source_mask(groups: pd.DataFrame) -> np.ndarray:
    """Identify only explicitly allowlisted, independently real flight rows."""

    return effective_source_types(groups) == "real"


def unknown_source_mask(groups: pd.DataFrame) -> np.ndarray:
    """Identify provenance that must be resolved before evaluation or release."""

    return effective_source_types(groups) == "unknown"


def require_known_source_types(groups: pd.DataFrame) -> np.ndarray:
    """Return normalized types or reject provenance that is not explicit."""

    effective = effective_source_types(groups)
    unknown_positions = np.flatnonzero(effective == "unknown")
    if len(unknown_positions):
        preview = ", ".join(str(int(index)) for index in unknown_positions[:10])
        raise ValueError(
            "Unknown source provenance at row positions "
            + preview
            + "; explicitly classify each row as real, SITL, HIL, or simulation."
        )
    return effective


def canonical_source_group(log_entry: Mapping[str, object], filename: str = "") -> str:
    """Return a stable incident group key for a ground-truth entry.

    Explicit ``source_group``/``incident_id`` values take precedence.  For
    downloaded forum/GitHub logs, the canonical source URL is a safe default:
    multiple attachments from one incident must stay in the same split.  URLs
    without a usable host/path are intentionally ignored so unrelated logs do
    not collapse into one group.  Synthetic/local logs fall back to filename.
    """

    for field in ("source_group", "incident_id", "case_id"):
        value = str(log_entry.get(field, "") or "").strip()
        if value:
            return f"incident:{value}"

    raw_url = str(log_entry.get("source_url", "") or "").strip()
    if raw_url and raw_url.upper() != "N/A":
        try:
            parts = urlsplit(raw_url)
            host = (parts.netloc or "").lower()
            path = (parts.path or "").rstrip("/")
            # Keep semantically meaningful query keys while dropping common
            # cache/download parameters that should not create new incidents.
            query = [
                (key, value)
                for key, value in parse_qsl(parts.query, keep_blank_values=True)
                if key.lower() not in {"download", "dl", "raw", "token", "utm_source", "utm_medium"}
            ]
            if host and path:
                query_text = urlencode(sorted(query))
                canonical = urlunsplit(("https", host, path, query_text, ""))
                return f"url:{canonical}"
        except ValueError:
            # A malformed URL is provenance metadata, not a reason to abort
            # importing an otherwise parseable local log.
            pass

    name = str(filename or log_entry.get("filename", "") or "").strip()
    return f"file:{name}" if name else "file:unknown"


def has_explicit_source_group(log_entry: Mapping[str, object]) -> bool:
    """Whether provenance supplied an incident key instead of a URL fallback."""

    return any(
        bool(str(log_entry.get(field, "") or "").strip())
        for field in ("source_group", "incident_id", "case_id")
    )


def primary_label_for_row(
    label_row: Mapping[str, object] | pd.Series,
    preferred: object = "",
    allowed: Sequence[str] | None = None,
) -> str:
    """Resolve one root-cause label without losing source ordering.

    Ground truth can contain several labels, but the classifier is currently
    single-target.  ``preferred`` is the explicit primary label emitted by
    the dataset builder.  If an old dataset has no primary column, preserving
    the previous deterministic column-order fallback keeps it readable while
    making the fallback visible to callers.
    """

    keys = list(allowed) if allowed is not None else list(label_row.keys())
    active = []
    for key in keys:
        try:
            value = label_row[key]
        except (KeyError, IndexError, TypeError):
            continue
        try:
            active_flag = float(value) == 1.0
        except (TypeError, ValueError):
            active_flag = str(value).strip().lower() in {"1", "true", "yes"}
        if active_flag:
            active.append(str(key))

    candidate = str(preferred or "").strip()
    if candidate and candidate in active:
        return candidate
    return active[0] if active else ""


def effective_group_values(groups: pd.DataFrame) -> np.ndarray:
    """Return incident-level groups, preferring the new ``source_group`` column."""

    if "source_group" in groups.columns:
        values = groups["source_group"].fillna("").astype(str).str.strip()
        if bool(values.ne("").all()):
            return values.to_numpy()
    if "source_log" not in groups.columns:
        raise ValueError("Groups CSV must contain source_log or source_group.")
    return groups["source_log"].fillna("").astype(str).to_numpy()


def effective_group_column(groups: pd.DataFrame) -> str:
    """Name the group column used for evaluation and leakage checks."""

    if "source_group" in groups.columns:
        values = groups["source_group"].fillna("").astype(str).str.strip()
        if bool(values.ne("").all()):
            return "source_group"
    if "source_log" in groups.columns:
        return "source_log"
    raise ValueError("Groups CSV must contain source_log or source_group.")


def ambiguous_group_labels(
    labels: pd.DataFrame,
    groups: pd.DataFrame,
    allowed: Sequence[str],
) -> dict[str, tuple[str, ...]]:
    """Find incident groups that contain more than one primary label.

    A source URL is only a conservative fallback grouping key.  If two
    attachments under that key have different root-cause labels, one label per
    incident cannot be evaluated honestly.  Callers should require explicit
    incident identifiers or exclude the entire ambiguous group.
    """

    if len(labels) != len(groups):
        raise ValueError("Labels and groups must have the same row count.")
    effective = effective_group_values(groups)
    mapping: dict[str, set[str]] = defaultdict(set)
    for position, (_, row) in enumerate(labels.iterrows()):
        preferred = (
            groups.iloc[position].get("primary_label", "")
            if "primary_label" in groups.columns
            else ""
        )
        primary = primary_label_for_row(row, preferred=preferred, allowed=allowed)
        if primary:
            mapping[str(effective[position])].add(primary)
    return {
        group: tuple(sorted(values))
        for group, values in mapping.items()
        if len(values) > 1
    }


def finite_sha256(path) -> str:
    """Hash a file in bounded chunks; kept here for dataset dedupe callers."""

    import hashlib

    digest = hashlib.sha256()
    with open(path, "rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
