"""Hash-bound raw temporal fidelity production from independent lineages."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .contracts import validate_contract
from .fidelity_statistics import STRATIFIER_FIELDS
from .gate_integrity import valid_sha256
from .schema import canonical_json_bytes, sha256_bytes, sha256_file
from .temporal_bounds import evaluate_temporal_summaries
from .temporal_metrics import summarize_temporal_record

DESIGN_SCHEMA = "logdiagnosis.temporal-fidelity-design/v1"
LEDGER_SCHEMA = "logdiagnosis.temporal-fidelity-ledger/v1"
REPORT_SCHEMA = "logdiagnosis.temporal-fidelity/v1"
DATASET_HASH_FIELDS = (
    "features_sha256",
    "labels_sha256",
    "groups_sha256",
    "split_ledger_sha256",
)


def _read_object(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"cannot read temporal fidelity input {source.name}: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise ValueError(f"temporal fidelity input {source.name} must be an object")
    return value


def _validate_design(design: dict[str, Any]) -> None:
    validate_contract(design, "temporal_fidelity_design.schema.json")
    for field in ("candidate_manifest_sha256", "feature_fidelity_design_sha256"):
        if not valid_sha256(design.get(field)):
            raise ValueError(f"temporal design has invalid {field}")
    channels = design["required_channels"]
    if len(channels) != len(set(channels)):
        raise ValueError("temporal design required channels are duplicated")
    sources = design["channel_sources"]
    if set(sources) != set(channels):
        raise ValueError(
            "temporal design channel sources differ from required channels"
        )
    if any(float(source["value_scale"]) == 0 for source in sources.values()):
        raise ValueError("temporal design channel value scale cannot be zero")
    seen_pairs: set[tuple[str, str]] = set()
    for pair in design["channel_pairs"]:
        one, two = pair["one"], pair["two"]
        if one == two or one not in channels or two not in channels:
            raise ValueError("temporal design channel pair is invalid")
        key = tuple(sorted((one, two)))
        if key in seen_pairs:
            raise ValueError("temporal design channel pair is duplicated")
        seen_pairs.add(key)
    lags = [float(value) for value in design["acf_lags_sec"]]
    if len(lags) != len(set(lags)) or any(value <= 0 for value in lags):
        raise ValueError("temporal design ACF lags must be unique and positive")
    band_names: set[str] = set()
    for band in design["psd_bands_hz"]:
        name = str(band["name"])
        low, high = float(band["low_hz"]), float(band["high_hz"])
        if name in band_names or low < 0 or high <= low:
            raise ValueError("temporal design PSD band is invalid")
        band_names.add(name)
    keys: set[tuple[str, ...]] = set()
    for stratum in design["required_strata"]:
        key = tuple(str(stratum.get(name, "")).strip() for name in STRATIFIER_FIELDS)
        if any(not value for value in key) or key in keys:
            raise ValueError("temporal design strata are blank or duplicated")
        keys.add(key)


def load_temporal_design(path: str | Path) -> dict[str, Any]:
    design = _read_object(path)
    _validate_design(design)
    return design


def _validate_ledger(
    ledger: dict[str, Any], design: dict[str, Any], design_path: str | Path
) -> None:
    validate_contract(ledger, "temporal_fidelity_ledger.schema.json")
    if ledger.get("candidate_manifest_sha256") != design.get(
        "candidate_manifest_sha256"
    ):
        raise ValueError("temporal ledger belongs to a different candidate")
    if ledger.get("temporal_design_sha256") != sha256_file(design_path):
        raise ValueError("temporal ledger is not bound to the exact temporal design")
    dataset = ledger.get("dataset", {})
    if any(not valid_sha256(dataset.get(field)) for field in DATASET_HASH_FIELDS):
        raise ValueError("temporal ledger has invalid dataset hashes")
    roots_by_domain: dict[str, str] = {}
    clusters: dict[str, tuple[str, str]] = {}
    artifacts: set[str] = set()
    units: set[tuple[str, str, tuple[str, ...]]] = set()
    for record in ledger["records"]:
        domain = record["domain"]
        root = record["lineage_root_id"].strip()
        cluster = record["near_duplicate_cluster_id"].strip()
        artifact = record["source_artifact_sha256"]
        if not root or not cluster or not valid_sha256(artifact):
            raise ValueError("temporal ledger record has invalid identity evidence")
        previous_domain = roots_by_domain.setdefault(root, domain)
        if previous_domain != domain:
            raise ValueError(
                "temporal lineage appears in both real and synthetic domains"
            )
        previous_cluster = clusters.setdefault(cluster, (root, domain))
        if previous_cluster != (root, domain):
            raise ValueError(
                "temporal near-duplicate cluster crosses independent units"
            )
        if artifact in artifacts:
            raise ValueError("temporal source artifact is duplicated")
        artifacts.add(artifact)
        stratum = record["stratum"]
        key = tuple(str(stratum.get(name, "")).strip() for name in STRATIFIER_FIELDS)
        if any(not value for value in key):
            raise ValueError("temporal ledger record has incomplete stratum metadata")
        unit = (domain, root, key)
        if unit in units:
            raise ValueError("temporal ledger duplicates a lineage-stratum unit")
        units.add(unit)


def _validate_dataset_identity(
    ledger: dict[str, Any],
    *,
    features_csv: str | Path,
    labels_csv: str | Path,
    groups_csv: str | Path,
    split_ledger_path: str | Path,
) -> None:
    paths = {
        "features_sha256": features_csv,
        "labels_sha256": labels_csv,
        "groups_sha256": groups_csv,
        "split_ledger_sha256": split_ledger_path,
    }
    for field, path in paths.items():
        if ledger["dataset"].get(field) != sha256_file(path):
            raise ValueError(f"temporal ledger dataset mismatch for {field}")
    groups = pd.read_csv(groups_csv)
    required_columns = {
        "lineage_root_id",
        "source_type",
        "sha256",
        "near_duplicate_cluster_id",
        "verification_status",
        *STRATIFIER_FIELDS,
    }
    missing = sorted(required_columns - set(groups.columns))
    if missing:
        raise ValueError("temporal groups CSV lacks " + ", ".join(missing))
    normalized = groups.fillna("").astype(str)
    synthetic_types = {"sitl", "hil", "simulation"}
    for record in ledger["records"]:
        root = record["lineage_root_id"]
        rows = normalized[normalized["lineage_root_id"].str.strip() == root]
        expected_domain = record["domain"]
        rows = rows[
            rows["source_type"]
            .str.strip()
            .map(
                lambda value: (
                    "real"
                    if value == "real"
                    else "synthetic"
                    if value in synthetic_types
                    else "unknown"
                )
            )
            == expected_domain
        ]
        rows = rows[
            (rows["sha256"].str.strip() == record["source_artifact_sha256"])
            & (
                rows["near_duplicate_cluster_id"].str.strip()
                == record["near_duplicate_cluster_id"]
            )
        ]
        for name in STRATIFIER_FIELDS:
            rows = rows[rows[name].str.strip() == str(record["stratum"][name]).strip()]
        if expected_domain == "synthetic":
            rows = rows[rows["verification_status"].str.strip() == "accepted"]
        if rows.empty:
            raise ValueError(
                "temporal record identity/provenance differs from the bound groups CSV"
            )


def build_temporal_fidelity_report(
    ledger_path: str | Path,
    design_path: str | Path,
    *,
    features_csv: str | Path,
    labels_csv: str | Path,
    groups_csv: str | Path,
    split_ledger_path: str | Path,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    """Compute a non-promoting temporal fidelity report from exact inputs."""

    design = load_temporal_design(design_path)
    ledger = _read_object(ledger_path)
    _validate_ledger(ledger, design, design_path)
    _validate_dataset_identity(
        ledger,
        features_csv=features_csv,
        labels_csv=labels_csv,
        groups_csv=groups_csv,
        split_ledger_path=split_ledger_path,
    )
    summaries: list[dict[str, Any]] = []
    metric_names: list[str] | None = None
    for record in ledger["records"]:
        metrics = summarize_temporal_record(record, design)
        names = sorted(metrics)
        if metric_names is None:
            metric_names = names
        elif names != metric_names:
            raise ValueError("temporal records produce inconsistent metric families")
        summaries.append(
            {
                "domain": record["domain"],
                "lineage_root_id": record["lineage_root_id"],
                "stratum": record["stratum"],
                "metrics": metrics,
            }
        )
    evaluation = evaluate_temporal_summaries(summaries, design)
    report = {
        "schema": REPORT_SCHEMA,
        "candidate_manifest_sha256": design["candidate_manifest_sha256"],
        "feature_fidelity_design_sha256": design["feature_fidelity_design_sha256"],
        "temporal_design_sha256": sha256_file(design_path),
        "temporal_ledger_sha256": sha256_file(ledger_path),
        "temporal_method_config_sha256": sha256_bytes(
            canonical_json_bytes(
                {
                    key: design[key]
                    for key in (
                        "required_channels",
                        "channel_sources",
                        "channel_pairs",
                        "acf_lags_sec",
                        "psd_bands_hz",
                        "maximum_cross_channel_lag_sec",
                        "require_transition_timing",
                        "bootstrap_draws",
                        "seed",
                    )
                }
            )
        ),
        "dataset": ledger["dataset"],
        "dataset_identity_verified": True,
        "real_lineages": len(
            {
                row["lineage_root_id"]
                for row in ledger["records"]
                if row["domain"] == "real"
            }
        ),
        "synthetic_lineages": len(
            {
                row["lineage_root_id"]
                for row in ledger["records"]
                if row["domain"] == "synthetic"
            }
        ),
        "near_duplicate_audit_pass": True,
        **evaluation,
        "release_authorized": False,
        "accuracy_claim": "not_demonstrated",
    }
    validate_contract(report, "temporal_fidelity_report.schema.json")
    if output_path is not None:
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
    return report


def validate_temporal_fidelity_report(
    report_path: str | Path,
    ledger_path: str | Path,
    design_path: str | Path,
    *,
    features_csv: str | Path,
    labels_csv: str | Path,
    groups_csv: str | Path,
    split_ledger_path: str | Path,
) -> dict[str, Any]:
    supplied = _read_object(report_path)
    recomputed = build_temporal_fidelity_report(
        ledger_path,
        design_path,
        features_csv=features_csv,
        labels_csv=labels_csv,
        groups_csv=groups_csv,
        split_ledger_path=split_ledger_path,
    )
    if supplied != recomputed:
        raise ValueError("temporal fidelity report differs from exact recomputation")
    return recomputed
