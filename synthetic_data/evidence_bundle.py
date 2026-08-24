"""Programmatic assembly of sealed acceptance-evidence bundles.

Manual JSON composition is rejected: every field is either supplied as a
machine-readable source report or computed here. The emitted bundle is an
unsigned draft until an independent authority attaches a trusted receipt;
``release_authorized`` is always false at build time.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping

from .gate_integrity import (
    CANDIDATE_HASH_FIELDS,
    EVIDENCE_DOMAINS,
    EVIDENCE_SCHEMA,
    evidence_binding_sha256,
    metrics_bundle_sha256,
    valid_sha256,
)
from .contracts import validate_contract
from .schema import canonical_json_bytes, sha256_bytes

BUNDLE_SCHEMA = "logdiagnosis.synthetic-evidence-bundle/v1"


def _reject_non_finite(value: Any, path: str) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"bundle input contains a non-finite number at {path}")
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_non_finite(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_non_finite(item, f"{path}[{index}]")


def _require_key_sets(
    candidate: Mapping[str, Any],
    domains: Mapping[str, Mapping[str, Any]],
) -> None:
    classes = list(candidate.get("declared_classes", []))
    scenarios = list(candidate.get("required_scenarios", []))
    if not classes or not scenarios:
        raise ValueError("candidate must declare classes and required scenarios")
    utility = domains.get("utility", {})
    for map_name in (
        "per_class_recall_delta_lower_95",
        "per_class_confirmation_lineages",
    ):
        per_class = utility.get(map_name, {})
        if per_class and set(per_class) != set(classes):
            raise ValueError(
                f"utility {map_name} key set differs from the declared classes"
            )
    execution = domains.get("execution", {})
    manifestation = execution.get("fault_manifestation", {}).get("by_scenario", {})
    if manifestation and set(manifestation) != set(scenarios):
        raise ValueError(
            "fault_manifestation scenario key set differs from the candidate"
        )
    calibration = domains.get("calibration", {})
    lineage_support = calibration.get("per_class_real_lineages", {})
    if lineage_support and set(lineage_support) != set(classes):
        raise ValueError(
            "calibration per-class key set differs from the declared classes"
        )


def assemble_evidence_bundle(
    *,
    candidate: Mapping[str, Any],
    confirmation_cohort_sha256: str,
    confirmation_report: Mapping[str, Any],
    domain_reports: Mapping[str, Mapping[str, Any]],
    source_report_sha256: Mapping[str, str] | None = None,
    authority_receipt: Mapping[str, Any] | None = None,
    confirmation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble, bind, and seal-draft one common-candidate evidence envelope."""

    if not valid_sha256(confirmation_cohort_sha256):
        raise ValueError("confirmation cohort sha256 is missing or malformed")
    validate_contract(confirmation_report, "confirmation_report.schema.json")
    unknown = set(domain_reports) - set(EVIDENCE_DOMAINS)
    missing = set(EVIDENCE_DOMAINS) - set(domain_reports)
    if unknown or missing:
        raise ValueError(
            f"domain reports mismatch: unknown={sorted(unknown)}, "
            f"missing={sorted(missing)}"
        )
    for name, report in domain_reports.items():
        if not isinstance(report, Mapping):
            raise ValueError(f"domain report {name} must be an object")
        _reject_non_finite(report, name)
        bound_candidate = report.get("candidate_manifest_sha256")
        if bound_candidate is not None and bound_candidate != candidate.get(
            "manifest_sha256"
        ):
            raise ValueError(f"domain report {name} belongs to a different candidate")

    candidate_block = dict(candidate)
    missing_hashes = [
        field
        for field in CANDIDATE_HASH_FIELDS
        if not valid_sha256(candidate_block.get(field))
    ]
    if missing_hashes:
        raise ValueError(
            "candidate block lacks valid sha256 bindings: " + ", ".join(missing_hashes)
        )
    _require_key_sets(candidate_block, domain_reports)
    report = dict(confirmation_report)
    if report.get("confirmation_cohort_sha256") != confirmation_cohort_sha256:
        raise ValueError("confirmation report belongs to a different cohort")
    if report.get("candidate_manifest_sha256") != candidate_block.get(
        "manifest_sha256"
    ):
        raise ValueError("confirmation report belongs to a different candidate")
    if report.get("prediction_ledger_sha256") != candidate_block.get(
        "prediction_ledger_sha256"
    ):
        raise ValueError("candidate is bound to a different confirmation ledger")
    if report.get("development_split_ledger_sha256") != candidate_block.get(
        "split_ledger_sha256"
    ):
        raise ValueError("confirmation report uses a different development split")
    if report.get("declared_classes") != candidate_block.get("declared_classes"):
        raise ValueError("confirmation report class order differs from the candidate")
    if report.get("utility") != domain_reports.get("utility"):
        raise ValueError("utility report is not the computed confirmation utility")

    source_hashes = source_report_sha256 or {}
    source_reports = {
        domain: str(source_hashes.get(domain, "")) for domain in EVIDENCE_DOMAINS
    }
    invalid_sources = [
        domain for domain, digest in source_reports.items() if not valid_sha256(digest)
    ]
    if invalid_sources:
        raise ValueError(
            "source report hashes are missing or malformed: "
            + ", ".join(sorted(invalid_sources))
        )

    evidence: dict[str, Any] = {
        "schema": EVIDENCE_SCHEMA,
        "candidate": candidate_block,
        "source_reports": source_reports,
        "provenance": dict(domain_reports["provenance"]),
        "execution": dict(domain_reports["execution"]),
        "utility": dict(domain_reports["utility"]),
        "calibration": dict(domain_reports["calibration"]),
        "safety": dict(domain_reports["safety"]),
        "fidelity": dict(domain_reports["fidelity"]),
        "ood": dict(domain_reports["ood"]),
        "privacy": dict(domain_reports["privacy"]),
        "reproducibility": dict(domain_reports["reproducibility"]),
        "confirmation": {
            "confirmation_cohort_sha256": confirmation_cohort_sha256,
        },
    }
    protocol = report["protocol"]
    confirmation_block: dict[str, Any] = {
        "confirmation_cohort_sha256": confirmation_cohort_sha256,
        "prediction_ledger_sha256": report["prediction_ledger_sha256"],
        "confirmation_report_content_sha256": sha256_bytes(
            canonical_json_bytes(report)
        ),
        **protocol,
        "report": report,
    }
    if confirmation is not None:
        unknown_confirmation = set(confirmation) - set(confirmation_block)
        conflicts = [
            key
            for key, value in confirmation.items()
            if key in confirmation_block and value != confirmation_block[key]
        ]
        if unknown_confirmation or conflicts:
            raise ValueError(
                "manual confirmation fields differ from the computed report"
            )
    evidence["confirmation"] = confirmation_block
    metrics_hash = metrics_bundle_sha256(evidence)
    if authority_receipt is not None:
        receipt = dict(authority_receipt)
        if receipt.get("metrics_bundle_sha256") != metrics_hash:
            raise ValueError("authority receipt is bound to a different metrics bundle")
        if receipt.get("candidate_manifest_sha256") != candidate_block.get(
            "manifest_sha256"
        ):
            raise ValueError(
                "authority receipt is bound to a different candidate manifest"
            )
        if receipt.get("confirmation_cohort_sha256") != confirmation_cohort_sha256:
            raise ValueError(
                "authority receipt is bound to a different confirmation cohort"
            )
    if authority_receipt is not None:
        confirmation_block["authority_receipt"] = dict(authority_receipt)
        confirmation_block["authority_receipt_sha256"] = sha256_bytes(
            canonical_json_bytes(dict(authority_receipt))
        )
    binding = evidence_binding_sha256(evidence)
    evidence["evidence_binding_sha256"] = binding
    for domain in EVIDENCE_DOMAINS:
        evidence[domain]["evidence_binding_sha256"] = binding

    bundle = {
        "schema": BUNDLE_SCHEMA,
        "bundle_status": (
            "receipt_attached" if authority_receipt is not None else "draft_unsigned"
        ),
        "release_authorized": False,
        "metrics_bundle_sha256": metrics_hash,
        "evidence_binding_sha256": binding,
        "evidence": evidence,
    }
    return bundle


def load_domain_reports(paths: Mapping[str, str | Path]) -> dict[str, dict]:
    """Load and hash every per-domain source report from disk."""

    reports: dict[str, dict] = {}
    digests: dict[str, str] = {}

    def _sha256_file(path: Path) -> str:
        import hashlib

        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    for domain, raw_path in paths.items():
        path = Path(raw_path)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"cannot read {domain} report: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"{domain} report root must be an object")
        reports[domain] = payload
        digests[domain] = _sha256_file(path)
    return {"reports": reports, "sha256": digests}
