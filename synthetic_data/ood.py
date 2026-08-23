"""Machine-computed out-of-distribution evidence producers.

Two layers live here:

- ``build_ood_report`` consumes a preregistered
  ``logdiagnosis.ood-evaluation-design/v1`` plus an
  ``logdiagnosis.ood-prediction-ledger/v1`` and emits gate-ready evidence
  with frozen-threshold binding, near-duplicate audits, per-domain support
  accounting, lineage-bootstrap bounds, and end-to-end runtime route checks.
- ``compute_ood_evidence`` is the raw scorer over supplied score maps when a
  caller already holds frozen inputs.

Every number is computed; nothing is manually entered. Resampling units are
lineages (never windows). Output field names mirror the acceptance-policy
OOD block so the bundle builder can map reports verbatim.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.metrics import roc_auc_score

OOD_SCHEMA = "logdiagnosis.synthetic-ood-evidence/v1"
DESIGN_SCHEMA = "logdiagnosis.ood-evaluation-design/v1"
LEDGER_SCHEMA = "logdiagnosis.ood-prediction-ledger/v1"
DEFAULT_CONFIDENCE = 0.95
DEFAULT_BOOTSTRAP_DRAWS = 2000

ROLE_THRESHOLD_CALIBRATION = "id_threshold_calibration"
ROLE_ID_EVALUATION = "id_evaluation"
ROLE_OOD_EVALUATION = "ood_evaluation"
ID_DOMAIN = "in_distribution"


# ---------------------------------------------------------------------------
# Shared numeric helpers
# ---------------------------------------------------------------------------


def _is_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _auroc(id_scores: np.ndarray, ood_scores: np.ndarray) -> float:
    labels = np.concatenate(
        [np.zeros(id_scores.size, dtype=int), np.ones(ood_scores.size, dtype=int)]
    )
    values = np.concatenate([id_scores, ood_scores])
    return float(roc_auc_score(labels, values))


def _detection_at_fpr_threshold(
    id_scores: np.ndarray, ood_scores: np.ndarray, *, threshold: float
) -> float:
    return float(np.mean(ood_scores >= threshold))


# ---------------------------------------------------------------------------
# Frozen design / ledger layer (canonical gate-facing API)
# ---------------------------------------------------------------------------


def threshold_config_sha256(design: Mapping[str, Any]) -> str:
    """Bind the frozen operating point and its selection provenance."""

    payload = {
        key: design.get(key)
        for key in (
            "schema",
            "candidate_manifest_sha256",
            "confirmation_cohort_sha256",
            "required_domains",
            "minimum_lineages_per_domain",
            "minimum_id_threshold_lineages",
            "minimum_id_evaluation_lineages",
            "id_false_positive_rate_target",
            "frozen_threshold",
            "threshold_selection_receipt_sha256",
            "frozen_before_evaluation",
        )
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def _load_json(path_or_obj: Any) -> dict[str, Any]:
    if isinstance(path_or_obj, (str, Path)):
        try:
            data = json.loads(Path(path_or_obj).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"cannot read JSON input: {exc}") from exc
    elif isinstance(path_or_obj, Mapping):
        data = dict(path_or_obj)
    else:
        raise ValueError("expected a path or mapping")
    if not isinstance(data, dict):
        raise ValueError("JSON root must be an object")
    return data


def _validate_design(design: Mapping[str, Any]) -> None:
    if design.get("schema") != DESIGN_SCHEMA:
        raise ValueError("unsupported OOD evaluation design schema")
    domains = design.get("required_domains")
    if (
        not isinstance(domains, list)
        or not domains
        or not all(isinstance(d, str) and d for d in domains)
    ):
        raise ValueError("design requires a non-empty required_domains list")
    for key in (
        "minimum_lineages_per_domain",
        "minimum_id_threshold_lineages",
        "minimum_id_evaluation_lineages",
    ):
        value = design.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"design {key} must be a positive integer")
    target = design.get("id_false_positive_rate_target")
    if isinstance(target, bool) or not 0.0 < float(target) < 1.0:
        raise ValueError("design id_false_positive_rate_target must be in (0,1)")
    threshold = design.get("frozen_threshold")
    if not _is_number(threshold):
        raise ValueError("design frozen_threshold must be a finite number")
    if design.get("frozen_before_evaluation") is not True:
        raise ValueError("design threshold must be marked frozen_before_evaluation")
    if not str(design.get("threshold_selection_receipt_sha256", "")):
        raise ValueError("design lacks threshold selection receipt")


def build_ood_report(ledger_input: Any, design_input: Any) -> dict[str, Any]:
    """Compute the gate-facing OOD evidence block from sealed inputs."""

    ledger = _load_json(ledger_input)
    design = _load_json(design_input)
    _validate_design(design)
    if ledger.get("schema") != LEDGER_SCHEMA:
        raise ValueError("unsupported OOD prediction ledger schema")

    candidate_sha = design.get("candidate_manifest_sha256")
    cohort_sha = design.get("confirmation_cohort_sha256")
    if (
        ledger.get("candidate_manifest_sha256") != candidate_sha
        or ledger.get("confirmation_cohort_sha256") != cohort_sha
    ):
        raise ValueError(
            "ledger is bound to a different candidate or confirmation cohort"
        )

    # Near-duplicate audit: one cluster id may never span multiple units.
    seen_clusters: set[str] = set()
    records = ledger.get("records")
    if not isinstance(records, list) or not records:
        raise ValueError("ledger contains no records")
    for record in records:
        cluster = str(record.get("near_duplicate_cluster_id", "") or "")
        if cluster:
            if cluster in seen_clusters:
                raise ValueError(
                    f"near-duplicate cluster spans multiple units: {cluster}"
                )
            seen_clusters.add(cluster)

    threshold_hash = threshold_config_sha256(design)
    frozen_threshold = float(design["frozen_threshold"])
    runtime_action = str(design.get("runtime_action", ""))

    cal_scores: list[float] = []
    id_eval_scores: list[float] = []
    domain_scores: dict[str, list[float]] = {
        domain: [] for domain in design["required_domains"]
    }
    route_ok = True

    for record in records:
        role = str(record.get("role", ""))
        score = record.get("ood_score")
        if not _is_number(score):
            raise ValueError(
                f"record {record.get('lineage_root_id')!r} has no finite ood_score"
            )
        value = float(score)
        if role == ROLE_THRESHOLD_CALIBRATION:
            cal_scores.append(value)
        elif role == ROLE_ID_EVALUATION:
            if str(record.get("runtime_ood_threshold_sha256", "")) != threshold_hash:
                raise ValueError(
                    "id evaluation record is bound to a different frozen threshold"
                )
            flagged = value >= frozen_threshold
            expected_review = flagged
            expected_action = runtime_action if flagged else "normal_diagnosis"
            if (
                bool(record.get("runtime_requires_human_review")) != expected_review
                or str(record.get("runtime_action", "")) != expected_action
            ):
                route_ok = False
            id_eval_scores.append(value)
        elif role == ROLE_OOD_EVALUATION:
            domain = str(record.get("ood_domain", ""))
            if domain not in domain_scores:
                raise ValueError(f"ledger produced unregistered domain: {domain}")
            if str(record.get("runtime_ood_threshold_sha256", "")) != threshold_hash:
                raise ValueError("ood record is bound to a different frozen threshold")
            flagged = value >= frozen_threshold
            if flagged and (
                bool(record.get("runtime_requires_human_review")) is not True
                or str(record.get("runtime_action", "")) != runtime_action
            ):
                route_ok = False
            domain_scores[domain].append(value)
        else:
            raise ValueError(f"unknown ledger role: {role!r}")

    draws = int(design.get("bootstrap_draws", DEFAULT_BOOTSTRAP_DRAWS))
    confidence = float(design.get("confidence_level", DEFAULT_CONFIDENCE))
    seed = int(design.get("random_seed", 20260823))
    alpha = 1.0 - confidence

    id_array = np.asarray(id_eval_scores, dtype=float)
    per_domain: dict[str, Any] = {}
    for domain in sorted(domain_scores):
        values = np.asarray(domain_scores[domain], dtype=float)
        if values.size and id_array.size:
            rng = np.random.default_rng(seed + (hash(domain) % 2**32))
            auroc_draws = np.empty(draws)
            det_draws = np.empty(draws)
            for i in range(draws):
                ir = id_array[rng.integers(0, id_array.size, id_array.size)]
                orr = values[rng.integers(0, values.size, values.size)]
                auroc_draws[i] = _auroc(ir, orr)
                det_draws[i] = _detection_at_fpr_threshold(
                    ir, orr, threshold=frozen_threshold
                )
            per_domain[domain] = {
                "lineage_count": int(values.size),
                "auroc_point": _auroc(id_array, values),
                "auroc_lower": float(np.quantile(auroc_draws, alpha)),
                "detection_point": _detection_at_fpr_threshold(
                    id_array, values, threshold=frozen_threshold
                ),
                "detection_lower": float(np.quantile(det_draws, alpha)),
            }
        else:
            per_domain[domain] = {
                "lineage_count": 0,
                "auroc_point": None,
                "auroc_lower": None,
                "detection_point": None,
                "detection_lower": None,
            }

    minimum_domain = int(design["minimum_lineages_per_domain"])
    minimum_support_complete = all(
        item["lineage_count"] >= minimum_domain
        and item["lineage_count"] >= int(design["minimum_id_evaluation_lineages"])
        for item in per_domain.values()
    ) and len(cal_scores) >= int(design["minimum_id_threshold_lineages"])

    metrics_ready = minimum_support_complete
    auroc_lower = (
        min(item["auroc_lower"] for item in per_domain.values())
        if metrics_ready
        else None
    )
    detection_lower = (
        min(item["detection_lower"] for item in per_domain.values())
        if metrics_ready
        else None
    )

    return {
        "schema": OOD_SCHEMA,
        "candidate_manifest_sha256": candidate_sha,
        "confirmation_cohort_sha256": cohort_sha,
        "runtime_ood_threshold_sha256": threshold_hash,
        "id_threshold_lineage_count": len(cal_scores),
        "id_evaluation_lineage_count": int(id_array.size),
        "per_domain_lineages": {
            d: item["lineage_count"] for d, item in per_domain.items()
        },
        "per_domain": per_domain,
        "auroc_lower_95": auroc_lower,
        "detection_at_5pct_id_fpr_lower_95": detection_lower,
        "minimum_support_complete": minimum_support_complete,
        "runtime_abstention_route_test_pass": route_ok,
        "gate_ready": bool(minimum_support_complete and route_ok),
        "release_claim": "none",
    }


# ---------------------------------------------------------------------------
# Raw scorer over frozen score maps
# ---------------------------------------------------------------------------


def _validate_scores(
    id_scores: Mapping[str, float],
    ood_scores: Mapping[str, Mapping[str, float]],
) -> None:
    if not id_scores:
        raise ValueError("OOD evidence requires in-distribution scores")
    if not ood_scores:
        raise ValueError("OOD evidence requires at least one OOD domain")
    for domain, scores in ood_scores.items():
        if not scores:
            raise ValueError(f"OOD domain {domain} has no scores")
    for source, scores in (
        ("id", id_scores),
        *[(f"ood.{d}", s) for d, s in ood_scores.items()],
    ):
        for unit, value in scores.items():
            if not str(unit).strip():
                raise ValueError(f"{source} scores contain a blank lineage id")
            if not _is_number(value):
                raise ValueError(f"{source} score for {unit} is not a finite number")


def compute_ood_evidence(
    id_scores: Mapping[str, float],
    ood_scores: Mapping[str, Mapping[str, float]],
    *,
    id_fpr: float = 0.05,
    bootstrap_draws: int = DEFAULT_BOOTSTRAP_DRAWS,
    confidence: float = DEFAULT_CONFIDENCE,
    seed: int = 20260823,
    abstention_routes: Mapping[str, bool] | None = None,
) -> dict[str, Any]:
    """AUROC + detection-at-ID-FPR over score maps with lineage bootstraps."""

    _validate_scores(id_scores, ood_scores)
    if isinstance(id_fpr, bool) or not 0.0 < id_fpr < 1.0:
        raise ValueError("id_fpr must be strictly between 0 and 1")
    if bootstrap_draws < 1:
        raise ValueError("bootstrap_draws must be positive")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be strictly between 0 and 1")

    id_values = np.asarray([float(v) for v in id_scores.values()], dtype=float)
    per_domain: dict[str, Any] = {}
    alpha = 1.0 - confidence
    for domain in sorted(ood_scores):
        values = np.asarray(
            [float(v) for v in ood_scores[domain].values()], dtype=float
        )
        threshold = float(np.quantile(id_values, 1.0 - id_fpr, method="higher"))
        rng = np.random.default_rng(seed + (hash(domain) % 2**32))
        auroc_draws = np.empty(bootstrap_draws)
        det_draws = np.empty(bootstrap_draws)
        for draw in range(bootstrap_draws):
            ir = id_values[rng.integers(0, id_values.size, id_values.size)]
            orr = values[rng.integers(0, values.size, values.size)]
            auroc_draws[draw] = _auroc(ir, orr)
            det_draws[draw] = _detection_at_fpr_threshold(ir, orr, threshold=threshold)
        per_domain[domain] = {
            "lineage_count": int(values.size),
            "auroc_point": _auroc(id_values, values),
            "auroc_lower": float(np.quantile(auroc_draws, alpha)),
            "detection_at_5pct_id_fpr_point": _detection_at_fpr_threshold(
                id_values, values, threshold=threshold
            ),
            "detection_at_5pct_id_fpr_lower": float(np.quantile(det_draws, alpha)),
        }

    routing_pass = True
    if abstention_routes is not None:
        missing = [d for d in per_domain if d not in abstention_routes]
        if missing:
            raise ValueError(f"abstention routes missing for domains: {missing}")
        routing_pass = all(bool(abstention_routes[d]) for d in per_domain)

    return {
        "schema": OOD_SCHEMA,
        "id_lineage_count": int(id_values.size),
        "id_fpr": float(id_fpr),
        "confidence": float(confidence),
        "bootstrap_draws": int(bootstrap_draws),
        "per_domain_lineages": {
            d: item["lineage_count"] for d, item in per_domain.items()
        },
        "per_domain": per_domain,
        "auroc_lower_95": min(i["auroc_lower"] for i in per_domain.values()),
        "detection_at_5pct_id_fpr_lower_95": min(
            i["detection_at_5pct_id_fpr_lower"] for i in per_domain.values()
        ),
        "runtime_abstention_route_test_pass": routing_pass,
        "release_claim": "none",
    }
