"""Common-candidate and independent-confirmation bindings for gate evidence."""

from __future__ import annotations

import math
from typing import Any

from .contracts import validate_contract
from .schema import canonical_json_bytes, sha256_bytes

EVIDENCE_SCHEMA = "logdiagnosis.synthetic-acceptance-evidence/v2"
EVIDENCE_DOMAINS = (
    "provenance",
    "execution",
    "utility",
    "calibration",
    "safety",
    "fidelity",
    "ood",
    "privacy",
    "reproducibility",
)
CANDIDATE_HASH_FIELDS = (
    "manifest_sha256",
    "classifier_sha256",
    "features_sha256",
    "labels_sha256",
    "groups_sha256",
    "dataset_report_sha256",
    "split_ledger_sha256",
    "extraction_contract_sha256",
    "prediction_ledger_sha256",
    "code_snapshot_sha256",
    "dependency_lock_sha256",
)


def valid_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


def valid_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def valid_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def valid_rate(value: object) -> bool:
    return valid_number(value) and 0.0 <= float(value) <= 1.0


def evidence_binding_sha256(evidence: dict[str, Any]) -> str:
    confirmation = evidence.get("confirmation", {})
    metrics_bundle = metrics_bundle_sha256(evidence)
    basis = {
        "candidate": evidence.get("candidate"),
        "confirmation_cohort_sha256": confirmation.get(
            "confirmation_cohort_sha256"
        ),
        "declared_classes": evidence.get("candidate", {}).get("declared_classes"),
        "required_scenarios": evidence.get("candidate", {}).get(
            "required_scenarios"
        ),
        "metrics_bundle_sha256": metrics_bundle,
    }
    return sha256_bytes(canonical_json_bytes(basis))


def metrics_bundle_sha256(evidence: dict[str, Any]) -> str:
    """Bind domain metrics and confirmation evidence without receipt recursion."""

    confirmation = evidence.get("confirmation")
    confirmation_metrics = (
        {
            key: value
            for key, value in confirmation.items()
            if key not in {"authority_receipt", "authority_receipt_sha256"}
        }
        if isinstance(confirmation, dict)
        else confirmation
    )
    domain_metrics = {
        domain: {
            key: value
            for key, value in (evidence.get(domain) or {}).items()
            if key != "evidence_binding_sha256"
        }
        for domain in EVIDENCE_DOMAINS
    }
    return sha256_bytes(
        canonical_json_bytes(
            {
                "domains": domain_metrics,
                "source_reports": evidence.get("source_reports"),
                "confirmation": confirmation_metrics,
            }
        )
    )


def _confirmation_report_ok(
    evidence: dict[str, Any], candidate: object, confirmation: object
) -> bool:
    if not isinstance(candidate, dict) or not isinstance(confirmation, dict):
        return False
    report = confirmation.get("report")
    if not isinstance(report, dict):
        return False
    try:
        validate_contract(report, "confirmation_report.schema.json")
    except ValueError:
        return False
    protocol = report.get("protocol")
    if not isinstance(protocol, dict):
        return False
    protocol_fields = (
        "blinded",
        "candidates_evaluated",
        "use_count",
        "candidate_frozen_before_open",
        "classes_frozen_before_open",
        "precision_plan_frozen_before_open",
        "precision_plan_sha256",
    )
    utility = evidence.get("utility")
    bound_utility = (
        {key: value for key, value in utility.items() if key != "evidence_binding_sha256"}
        if isinstance(utility, dict)
        else utility
    )
    return bool(
        report.get("candidate_manifest_sha256") == candidate.get("manifest_sha256")
        and report.get("prediction_ledger_sha256")
        == candidate.get("prediction_ledger_sha256")
        and report.get("confirmation_cohort_sha256")
        == confirmation.get("confirmation_cohort_sha256")
        and report.get("development_split_ledger_sha256")
        == candidate.get("split_ledger_sha256")
        and report.get("declared_classes") == candidate.get("declared_classes")
        and report.get("utility") == bound_utility
        and report.get("utility_evidence_sha256")
        == sha256_bytes(canonical_json_bytes(bound_utility))
        and confirmation.get("confirmation_report_content_sha256")
        == sha256_bytes(canonical_json_bytes(report))
        and confirmation.get("prediction_ledger_sha256")
        == report.get("prediction_ledger_sha256")
        and all(confirmation.get(field) == protocol.get(field) for field in protocol_fields)
    )


def envelope_checks(
    evidence: dict[str, Any], policy: dict[str, Any]
) -> dict[str, Any]:
    candidate = evidence.get("candidate")
    confirmation = evidence.get("confirmation")
    expected_classes = policy.get("evaluation_protocol", {}).get(
        "declared_classes", []
    )
    expected_scenarios = policy.get("evaluation_protocol", {}).get(
        "required_scenarios", []
    )
    candidate_ok = isinstance(candidate, dict) and all(
        valid_sha256(candidate.get(field)) for field in CANDIDATE_HASH_FIELDS
    )
    taxonomy_ok = bool(
        isinstance(candidate, dict)
        and candidate.get("declared_classes") == expected_classes
        and candidate.get("required_scenarios") == expected_scenarios
    )
    cohort_ok = bool(
        isinstance(confirmation, dict)
        and valid_sha256(confirmation.get("confirmation_cohort_sha256"))
    )
    binding = evidence_binding_sha256(evidence)
    binding_ok = evidence.get("evidence_binding_sha256") == binding
    domains_ok = all(
        isinstance(evidence.get(domain), dict)
        and evidence[domain].get("evidence_binding_sha256") == binding
        for domain in EVIDENCE_DOMAINS
    )
    source_reports = evidence.get("source_reports")
    reports_ok = bool(
        isinstance(source_reports, dict)
        and set(source_reports) == set(EVIDENCE_DOMAINS)
        and all(valid_sha256(value) for value in source_reports.values())
    )
    confirmation_report_ok = _confirmation_report_ok(
        evidence, candidate, confirmation
    )

    authority_ok = False
    authority_hash: str | None = None
    if isinstance(confirmation, dict):
        receipt = confirmation.get("authority_receipt")
        if isinstance(receipt, dict):
            authority_hash = sha256_bytes(canonical_json_bytes(receipt))
            allowed = set(
                policy.get("evaluation_protocol", {}).get(
                    "authorized_confirmation_receipt_sha256", []
                )
            )
            authority_ok = bool(
                authority_hash in allowed
                and confirmation.get("authority_receipt_sha256") == authority_hash
                and isinstance(candidate, dict)
                and receipt.get("candidate_manifest_sha256")
                == candidate.get("manifest_sha256")
                and receipt.get("confirmation_cohort_sha256")
                == confirmation.get("confirmation_cohort_sha256")
                and receipt.get("evidence_binding_sha256") == binding
                and receipt.get("metrics_bundle_sha256")
                == metrics_bundle_sha256(evidence)
                and str(receipt.get("authority", "")).strip()
                and str(receipt.get("receipt_id", "")).strip()
            )
    return {
        "schema": evidence.get("schema") == EVIDENCE_SCHEMA,
        "candidate_hashes": candidate_ok,
        "frozen_taxonomy_and_scenarios": taxonomy_ok,
        "confirmation_cohort": cohort_ok,
        "common_binding": binding_ok and domains_ok,
        "source_report_hashes": reports_ok,
        "confirmation_prediction_contract": confirmation_report_ok,
        "allowlisted_authority_receipt": authority_ok,
        "computed_binding_sha256": binding,
        "computed_authority_receipt_sha256": authority_hash,
    }
