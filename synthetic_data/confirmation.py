"""Reproducible evidence from a one-time physical confirmation cohort."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from .contracts import validate_contract
from .schema import canonical_json_bytes, sha256_bytes, sha256_file
from .splits import SPLIT_SCHEMA

COHORT_SCHEMA = "logdiagnosis.confirmation-cohort-manifest/v1"
LEDGER_SCHEMA = "logdiagnosis.confirmation-predictions/v1"
REPORT_SCHEMA = "logdiagnosis.confirmation-report/v1"
AGGREGATION = "maximum raw class probability by lineage_root_id"
RECALL_INTERVAL_METHOD = "simultaneous_class_stratified_lineage_bootstrap"
MINIMUM_BOOTSTRAP_DRAWS = 1000


def _read_object(path: str | Path, name: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {name}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{name} root must be an object")
    return value


def _digest(values: set[str]) -> str:
    return sha256_bytes(canonical_json_bytes(sorted(values)))


def _label_schema_hash(classes: list[str]) -> str:
    return hashlib.sha256(json.dumps(classes, sort_keys=True).encode()).hexdigest()


def _unique_classes(value: object) -> list[str]:
    if not isinstance(value, list) or len(value) < 2:
        raise ValueError("confirmation contract needs at least two declared classes")
    classes = [str(item).strip() for item in value]
    if any(not item for item in classes) or len(classes) != len(set(classes)):
        raise ValueError("declared classes must be non-empty and unique")
    return classes


def _validate_target(row: Mapping[str, Any], classes: list[str]) -> int:
    class_id = row.get("target_class_id")
    if (
        not isinstance(class_id, int)
        or isinstance(class_id, bool)
        or class_id < 0
        or class_id >= len(classes)
        or row.get("target_class") != classes[class_id]
    ):
        raise ValueError("confirmation record target differs from the class order")
    return class_id


def _probabilities(
    row: Mapping[str, Any], field: str, classes: list[str]
) -> np.ndarray:
    values = row.get(field)
    if not isinstance(values, dict) or set(values) != set(classes):
        raise ValueError(f"{field} must cover the exact declared classes")
    result = np.asarray([values[name] for name in classes], dtype=float)
    if (
        result.shape != (len(classes),)
        or not np.isfinite(result).all()
        or np.any((result < 0.0) | (result > 1.0))
    ):
        raise ValueError(f"{field} contains an invalid probability")
    return result


def _manifest_bindings(
    candidate_manifest_path: str | Path,
    baseline_manifest_path: str | Path,
    development_groups_path: str | Path,
    development_split_path: str | Path,
    classes: list[str],
) -> tuple[str, str]:
    candidate = _read_object(candidate_manifest_path, "candidate manifest")
    baseline = _read_object(baseline_manifest_path, "baseline manifest")
    candidate_hash = sha256_file(candidate_manifest_path)
    baseline_hash = sha256_file(baseline_manifest_path)
    if (
        candidate.get("artifact_schema_version") != 3
        or candidate.get("release_status")
        != "development_candidate_requires_blinded_confirmation"
    ):
        raise ValueError("candidate manifest is not a schema-v3 frozen candidate")
    if baseline.get("artifact_schema_version") != 3:
        raise ValueError("baseline manifest is not schema-v3")
    training = candidate.get("training_inputs")
    if not isinstance(training, dict):
        raise ValueError("candidate manifest has no training-input bindings")
    if training.get("groups_sha256") != sha256_file(development_groups_path):
        raise ValueError("candidate manifest is bound to different development groups")
    if training.get("split_ledger_sha256") != sha256_file(development_split_path):
        raise ValueError("candidate manifest is bound to a different split ledger")
    if candidate.get("trained_label_schema_hash") != _label_schema_hash(classes):
        raise ValueError("candidate manifest declared-class order differs")
    if baseline.get("trained_label_schema_hash") != _label_schema_hash(classes):
        raise ValueError("baseline manifest declared-class order differs")
    return candidate_hash, baseline_hash


def _development_identity(
    groups_path: str | Path, split_path: str | Path
) -> tuple[set[str], set[str], set[str]]:
    split = _read_object(split_path, "development split ledger")
    if split.get("schema") != SPLIT_SCHEMA or split.get("frozen") is not True:
        raise ValueError("development split ledger is unsupported or not frozen")
    assignments = split.get("lineage_assignments")
    if not isinstance(assignments, dict) or not assignments:
        raise ValueError("development split ledger has no lineage assignments")
    groups = pd.read_csv(groups_path, keep_default_na=False)
    required = {"lineage_root_id", "source_type", "near_duplicate_cluster_id"}
    if not required.issubset(groups.columns):
        missing = sorted(required - set(groups.columns))
        raise ValueError("development groups lack columns: " + ", ".join(missing))
    lineages: set[str] = set()
    clusters: set[str] = set()
    artifacts: set[str] = set()
    real_lineages: set[str] = set()
    for _, row in groups.iterrows():
        lineage = str(row["lineage_root_id"]).strip()
        cluster = str(row["near_duplicate_cluster_id"]).strip()
        if not lineage or not cluster:
            raise ValueError("development provenance has a blank lineage or cluster")
        lineages.add(lineage)
        clusters.add(cluster)
        if str(row["source_type"]).strip() == "real":
            real_lineages.add(lineage)
        row_hashes = {
            str(row.get(field, "")).strip()
            for field in ("sha256", "artifact_sha256")
            if str(row.get(field, "")).strip()
        }
        if not row_hashes or any(
            len(value) != 64 or any(char not in "0123456789abcdef" for char in value)
            for value in row_hashes
        ):
            raise ValueError("development provenance has an invalid artifact hash")
        artifacts.update(row_hashes)
    if set(assignments) != real_lineages:
        raise ValueError("development split does not cover exactly the real lineages")
    return lineages, artifacts, clusters


def _validate_cohort(
    cohort: dict[str, Any], classes: list[str]
) -> dict[str, dict[str, Any]]:
    validate_contract(cohort, "confirmation_cohort_manifest.schema.json")
    if cohort.get("schema") != COHORT_SCHEMA:
        raise ValueError("confirmation cohort schema is unsupported")
    if cohort.get("declared_classes") != classes:
        raise ValueError("confirmation cohort class order differs")
    records = cohort["records"]
    roots = [str(row["lineage_root_id"]) for row in records]
    if roots != sorted(set(roots)):
        raise ValueError("confirmation cohort lineages must be unique and sorted")
    artifacts = [str(row["source_artifact_sha256"]) for row in records]
    clusters = [str(row["near_duplicate_cluster_id"]) for row in records]
    if len(artifacts) != len(set(artifacts)):
        raise ValueError("confirmation cohort reuses a source artifact")
    if len(clusters) != len(set(clusters)):
        raise ValueError("confirmation cohort contains a near-duplicate cluster")
    for row in records:
        _validate_target(row, classes)
    support = Counter(str(row["target_class"]) for row in records)
    if set(support) != set(classes) or min(support.values()) < 2:
        raise ValueError("confirmation cohort needs at least two lineages per class")
    return {str(row["lineage_root_id"]): row for row in records}


def _validate_ledger(
    ledger: dict[str, Any],
    cohort_rows: Mapping[str, Mapping[str, Any]],
    classes: list[str],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    validate_contract(ledger, "confirmation_prediction_ledger.schema.json")
    if ledger.get("schema") != LEDGER_SCHEMA or ledger.get("aggregation") != AGGREGATION:
        raise ValueError("confirmation prediction ledger is unsupported")
    if ledger.get("declared_classes") != classes:
        raise ValueError("confirmation prediction class order differs")
    records = ledger["records"]
    roots = [str(row["lineage_root_id"]) for row in records]
    if roots != sorted(set(roots)) or roots != list(cohort_rows):
        raise ValueError("prediction ledger does not cover the exact frozen cohort")
    targets: list[int] = []
    candidate: list[np.ndarray] = []
    baseline: list[np.ndarray] = []
    for row in records:
        root = str(row["lineage_root_id"])
        cohort = cohort_rows[root]
        for field in (
            "target_class",
            "target_class_id",
            "source_artifact_sha256",
            "near_duplicate_cluster_id",
        ):
            if row.get(field) != cohort.get(field):
                raise ValueError(f"prediction ledger changes cohort field {field}")
        targets.append(_validate_target(row, classes))
        candidate.append(_probabilities(row, "candidate_probabilities_by_class", classes))
        baseline.append(_probabilities(row, "baseline_probabilities_by_class", classes))
    return np.asarray(targets), np.asarray(candidate), np.asarray(baseline)


def _macro_f1(target: np.ndarray, predicted: np.ndarray, class_count: int) -> float:
    values: list[float] = []
    for class_id in range(class_count):
        tp = int(np.sum((target == class_id) & (predicted == class_id)))
        fp = int(np.sum((target != class_id) & (predicted == class_id)))
        fn = int(np.sum((target == class_id) & (predicted != class_id)))
        denominator = 2 * tp + fp + fn
        values.append(0.0 if denominator == 0 else (2.0 * tp) / denominator)
    return float(np.mean(values))


def _recalls(target: np.ndarray, predicted: np.ndarray, class_count: int) -> np.ndarray:
    values = np.zeros(class_count, dtype=float)
    for class_id in range(class_count):
        positions = target == class_id
        values[class_id] = float(np.mean(predicted[positions] == class_id))
    return values


def _utility(
    target: np.ndarray,
    candidate_scores: np.ndarray,
    baseline_scores: np.ndarray,
    classes: list[str],
    *,
    draws: int,
    seed: int,
) -> dict[str, Any]:
    if draws < MINIMUM_BOOTSTRAP_DRAWS:
        raise ValueError(f"confirmation bootstrap requires at least {MINIMUM_BOOTSTRAP_DRAWS} draws")
    candidate = np.argmax(candidate_scores, axis=1)
    baseline = np.argmax(baseline_scores, axis=1)
    class_count = len(classes)
    candidate_f1 = _macro_f1(target, candidate, class_count)
    baseline_f1 = _macro_f1(target, baseline, class_count)
    observed_recall_delta = _recalls(target, candidate, class_count) - _recalls(
        target, baseline, class_count
    )
    positions = [np.flatnonzero(target == class_id) for class_id in range(class_count)]
    rng = np.random.default_rng(seed)
    candidate_draws = np.empty(draws, dtype=float)
    delta_draws = np.empty(draws, dtype=float)
    recall_draws = np.empty((draws, class_count), dtype=float)
    for draw in range(draws):
        sample = np.concatenate(
            [rng.choice(item, size=len(item), replace=True) for item in positions]
        )
        candidate_draws[draw] = _macro_f1(target[sample], candidate[sample], class_count)
        base_value = _macro_f1(target[sample], baseline[sample], class_count)
        delta_draws[draw] = candidate_draws[draw] - base_value
        recall_draws[draw] = _recalls(
            target[sample], candidate[sample], class_count
        ) - _recalls(target[sample], baseline[sample], class_count)
    max_shortfall = np.max(observed_recall_delta - recall_draws, axis=1)
    simultaneous_radius = float(np.quantile(max_shortfall, 0.95))
    support = Counter(int(value) for value in target)
    return {
        "candidate_macro_f1": candidate_f1,
        "baseline_macro_f1": baseline_f1,
        "macro_f1_lower_95": float(np.quantile(candidate_draws, 0.025)),
        "per_class_confirmation_lineages": {
            name: int(support[class_id]) for class_id, name in enumerate(classes)
        },
        "paired_bootstrap": {
            "observed_delta_macro_f1": float(candidate_f1 - baseline_f1),
            "mean_delta_macro_f1": float(np.mean(delta_draws)),
            "lower_95": float(np.quantile(delta_draws, 0.025)),
            "upper_95": float(np.quantile(delta_draws, 0.975)),
            "draws": int(draws),
            "resampling_unit": "lineage_root_id",
            "stratified_by_declared_class": True,
        },
        "per_class_recall_delta_lower_95": {
            name: float(observed_recall_delta[class_id] - simultaneous_radius)
            for class_id, name in enumerate(classes)
        },
        "recall_interval_method": RECALL_INTERVAL_METHOD,
    }


def build_confirmation_report(
    prediction_ledger_path: str | Path,
    cohort_manifest_path: str | Path,
    candidate_manifest_path: str | Path,
    baseline_manifest_path: str | Path,
    development_groups_path: str | Path,
    development_split_path: str | Path,
    *,
    output_path: str | Path | None = None,
    bootstrap_draws: int = 10000,
    seed: int = 20260823,
) -> dict[str, Any]:
    """Validate identity and derive all confirmation utility metrics."""

    ledger = _read_object(prediction_ledger_path, "confirmation prediction ledger")
    cohort = _read_object(cohort_manifest_path, "confirmation cohort manifest")
    classes = _unique_classes(ledger.get("declared_classes"))
    candidate_hash, baseline_hash = _manifest_bindings(
        candidate_manifest_path,
        baseline_manifest_path,
        development_groups_path,
        development_split_path,
        classes,
    )
    split_hash = sha256_file(development_split_path)
    cohort_hash = sha256_file(cohort_manifest_path)
    bindings = {
        "candidate_manifest_sha256": candidate_hash,
        "baseline_manifest_sha256": baseline_hash,
        "development_split_ledger_sha256": split_hash,
    }
    for name, expected in bindings.items():
        if ledger.get(name) != expected or cohort.get(name) != expected:
            raise ValueError(f"confirmation inputs disagree on {name}")
    if ledger.get("confirmation_cohort_sha256") != cohort_hash:
        raise ValueError("prediction ledger is bound to a different cohort manifest")
    cohort_rows = _validate_cohort(cohort, classes)
    target, candidate_scores, baseline_scores = _validate_ledger(
        ledger, cohort_rows, classes
    )
    development_lineages, development_artifacts, development_clusters = (
        _development_identity(development_groups_path, development_split_path)
    )
    cohort_lineages = set(cohort_rows)
    cohort_artifacts = {
        str(row["source_artifact_sha256"]) for row in cohort_rows.values()
    }
    cohort_clusters = {
        str(row["near_duplicate_cluster_id"]) for row in cohort_rows.values()
    }
    overlaps = {
        "development_overlap_count": len(cohort_lineages & development_lineages),
        "artifact_overlap_count": len(cohort_artifacts & development_artifacts),
        "near_duplicate_overlap_count": len(cohort_clusters & development_clusters),
    }
    if any(overlaps.values()):
        raise ValueError(f"confirmation cohort overlaps development evidence: {overlaps}")
    utility = _utility(
        target,
        candidate_scores,
        baseline_scores,
        classes,
        draws=int(bootstrap_draws),
        seed=int(seed),
    )
    method = {
        "aggregation": AGGREGATION,
        "absolute_interval_quantile": 0.025,
        "paired_interval_quantiles": [0.025, 0.975],
        "recall_interval_method": RECALL_INTERVAL_METHOD,
        "simultaneous_recall_quantile": 0.95,
        "resampling_unit": "lineage_root_id",
        "stratified_by_declared_class": True,
    }
    protocol_keys = (
        "blinded",
        "candidates_evaluated",
        "use_count",
        "candidate_frozen_before_open",
        "classes_frozen_before_open",
        "precision_plan_frozen_before_open",
        "precision_plan_sha256",
    )
    report = {
        "schema": REPORT_SCHEMA,
        **bindings,
        "confirmation_cohort_sha256": cohort_hash,
        "prediction_ledger_sha256": sha256_file(prediction_ledger_path),
        "development_groups_sha256": sha256_file(development_groups_path),
        "declared_classes": classes,
        "protocol": {key: cohort[key] for key in protocol_keys},
        "cohort_identity_verified": True,
        "physical_lineages_verified": True,
        **overlaps,
        "development_lineage_digest_sha256": _digest(development_lineages),
        "cohort_lineage_digest_sha256": _digest(cohort_lineages),
        "utility": utility,
        "utility_evidence_sha256": sha256_bytes(canonical_json_bytes(utility)),
        "method_config_sha256": sha256_bytes(canonical_json_bytes(method)),
        "bootstrap_seed": int(seed),
        "complete": True,
        "derived_from_prediction_ledger": True,
        "independent_authority_required": True,
        "non_promoting": True,
        "release_authorized": False,
        "accuracy_claim": "not_demonstrated_without_gate_and_authority",
    }
    validate_contract(report, "confirmation_report.schema.json")
    if output_path is not None:
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
    return report


def validate_confirmation_report(
    report_path: str | Path,
    prediction_ledger_path: str | Path,
    cohort_manifest_path: str | Path,
    candidate_manifest_path: str | Path,
    baseline_manifest_path: str | Path,
    development_groups_path: str | Path,
    development_split_path: str | Path,
) -> dict[str, Any]:
    """Exactly reproduce a saved report, including its frozen RNG settings."""

    observed = _read_object(report_path, "confirmation report")
    validate_contract(observed, "confirmation_report.schema.json")
    draws = observed.get("utility", {}).get("paired_bootstrap", {}).get("draws")
    seed = observed.get("bootstrap_seed")
    if not isinstance(draws, int) or isinstance(draws, bool):
        raise ValueError("confirmation report bootstrap draws are invalid")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("confirmation report bootstrap seed is invalid")
    reproduced = build_confirmation_report(
        prediction_ledger_path,
        cohort_manifest_path,
        candidate_manifest_path,
        baseline_manifest_path,
        development_groups_path,
        development_split_path,
        bootstrap_draws=draws,
        seed=seed,
    )
    if canonical_json_bytes(observed) != canonical_json_bytes(reproduced):
        raise ValueError("confirmation report differs from exact recomputation")
    return observed
