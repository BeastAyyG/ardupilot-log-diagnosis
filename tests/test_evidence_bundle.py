"""Goal 05: programmatic sealed acceptance-evidence bundle builder."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from synthetic_data.evidence_bundle import (
    assemble_evidence_bundle,
    load_domain_reports,
)
from synthetic_data.gate_integrity import (
    EVIDENCE_DOMAINS,
    evidence_binding_sha256,
    metrics_bundle_sha256,
)
from synthetic_data.gates import evaluate_acceptance

from test_acceptance_gates import _full_gate_evidence


@pytest.fixture()
def evidence() -> dict:
    return _full_gate_evidence()


def _split(evidence: dict) -> tuple[dict, dict[str, dict], dict[str, str]]:
    candidate = dict(evidence["candidate"])
    domains = {domain: dict(evidence[domain]) for domain in EVIDENCE_DOMAINS}
    for domain in EVIDENCE_DOMAINS:
        domains[domain].pop("evidence_binding_sha256", None)
    return candidate, domains, dict(evidence["source_reports"])


def _authority(evidence: dict, metrics_bundle: str) -> dict:
    return {
        "receipt_id": "authority-001",
        "authority": "independent-test-authority",
        "candidate_manifest_sha256": evidence["candidate"]["manifest_sha256"],
        "confirmation_cohort_sha256": evidence["confirmation"][
            "confirmation_cohort_sha256"
        ],
        "evidence_binding_sha256": evidence["evidence_binding_sha256"],
        "metrics_bundle_sha256": metrics_bundle,
    }


def test_assembled_bundle_reproduces_the_reference_binding(evidence) -> None:
    candidate, domains, sources = _split(evidence)
    bundle = assemble_evidence_bundle(
        candidate=candidate,
        confirmation_cohort_sha256=evidence["confirmation"][
            "confirmation_cohort_sha256"
        ],
        confirmation_report=evidence["confirmation"]["report"],
        domain_reports=domains,
        source_report_sha256=sources,
    )
    assert bundle["bundle_status"] == "draft_unsigned"
    assert bundle["release_authorized"] is False
    assert bundle["evidence_binding_sha256"] == evidence["evidence_binding_sha256"]
    rebuilt = bundle["evidence"]
    assert evidence_binding_sha256(rebuilt) == evidence["evidence_binding_sha256"]


def test_bundle_with_authority_receipt_passes_the_technical_gate(
    evidence, tmp_path
) -> None:

    from synthetic_data.schema import canonical_json_bytes, sha256_bytes

    candidate, domains, sources = _split(evidence)
    metrics_bundle = metrics_bundle_sha256(evidence)
    receipt = _authority(evidence, metrics_bundle)
    receipt["evidence_binding_sha256"] = evidence["evidence_binding_sha256"]
    receipt_sha = str(sha256_bytes(canonical_json_bytes(receipt)))

    policy = json.loads(
        (
            Path(__file__).parents[1]
            / "synthetic_data"
            / "configs"
            / "acceptance_gates.json"
        ).read_text(encoding="utf-8")
    )
    policy["evaluation_protocol"]["authorized_confirmation_receipt_sha256"] = [
        receipt_sha
    ]
    bundle = assemble_evidence_bundle(
        candidate=candidate,
        confirmation_cohort_sha256=evidence["confirmation"][
            "confirmation_cohort_sha256"
        ],
        confirmation_report=evidence["confirmation"]["report"],
        domain_reports=domains,
        source_report_sha256=sources,
        authority_receipt=receipt,
    )
    result = evaluate_acceptance(bundle["evidence"], policy)
    assert result["pass"] is True
    assert result["release_authorized"] is False


def test_missing_domain_or_foreign_candidate_is_refused(evidence) -> None:
    candidate, domains, sources = _split(evidence)

    with pytest.raises(ValueError, match="missing"):
        assemble_evidence_bundle(
            candidate=candidate,
            confirmation_cohort_sha256="c" * 64,
            confirmation_report=evidence["confirmation"]["report"],
            domain_reports={k: v for k, v in domains.items() if k != "privacy"},
            source_report_sha256=sources,
        )
    foreign = dict(domains["utility"], candidate_manifest_sha256="9" * 64)
    with pytest.raises(ValueError, match="different candidate"):
        assemble_evidence_bundle(
            candidate=candidate,
            confirmation_cohort_sha256="c" * 64,
            confirmation_report=evidence["confirmation"]["report"],
            domain_reports={**domains, "utility": foreign},
            source_report_sha256=sources,
        )


def test_non_finite_metrics_are_refused(evidence) -> None:
    candidate, domains, sources = _split(evidence)
    poisoned = dict(domains["safety"], false_critical_rate_upper_95=float("nan"))
    with pytest.raises(ValueError, match="non-finite"):
        assemble_evidence_bundle(
            candidate=candidate,
            confirmation_cohort_sha256="c" * 64,
            confirmation_report=evidence["confirmation"]["report"],
            domain_reports={**domains, "safety": poisoned},
            source_report_sha256=sources,
        )


def test_class_or_scenario_key_drift_is_refused(evidence) -> None:
    candidate, domains, sources = _split(evidence)
    drifted_utility = dict(domains["utility"])
    drifted_utility["per_class_confirmation_lineages"] = {
        key: value
        for key, value in drifted_utility["per_class_confirmation_lineages"].items()
        if key != "rc_failsafe"
    }
    with pytest.raises(ValueError, match="key set differs from the declared classes"):
        assemble_evidence_bundle(
            candidate=candidate,
            confirmation_cohort_sha256="c" * 64,
            confirmation_report=evidence["confirmation"]["report"],
            domain_reports={**domains, "utility": drifted_utility},
            source_report_sha256=sources,
        )
    drifted_execution = dict(domains["execution"])
    manifestation = dict(drifted_execution["fault_manifestation"]["by_scenario"])
    manifestation.pop("gps_quality_poor")
    drifted_execution["fault_manifestation"] = {
        **drifted_execution["fault_manifestation"],
        "by_scenario": manifestation,
    }
    with pytest.raises(ValueError, match="scenario key set"):
        assemble_evidence_bundle(
            candidate=candidate,
            confirmation_cohort_sha256="c" * 64,
            confirmation_report=evidence["confirmation"]["report"],
            domain_reports={**domains, "execution": drifted_execution},
            source_report_sha256=sources,
        )


def test_any_metric_mutation_changes_the_binding(evidence) -> None:
    candidate, domains, sources = _split(evidence)
    baseline = assemble_evidence_bundle(
        candidate=candidate,
        confirmation_cohort_sha256="c" * 64,
        confirmation_report=evidence["confirmation"]["report"],
        domain_reports=domains,
        source_report_sha256=sources,
    )
    mutated_utility = dict(domains["utility"], macro_f1_lower_95=0.74)
    assert baseline["evidence_binding_sha256"]
    with pytest.raises(ValueError, match="computed confirmation utility"):
        assemble_evidence_bundle(
            candidate=candidate,
            confirmation_cohort_sha256="c" * 64,
            confirmation_report=evidence["confirmation"]["report"],
            domain_reports={**domains, "utility": mutated_utility},
            source_report_sha256=sources,
        )


def test_authority_receipt_bound_to_other_inputs_is_refused(evidence) -> None:
    candidate, domains, sources = _split(evidence)
    metrics_bundle = metrics_bundle_sha256(evidence)
    receipt = _authority(evidence, metrics_bundle)
    with pytest.raises(ValueError, match="different cohort"):
        assemble_evidence_bundle(
            candidate=candidate,
            confirmation_cohort_sha256="d" * 64,
            confirmation_report=evidence["confirmation"]["report"],
            domain_reports=domains,
            source_report_sha256=sources,
            authority_receipt=receipt,
        )


def test_load_domain_reports_hashes_files(evidence, tmp_path) -> None:
    import hashlib

    paths = {}
    for domain in ("provenance", "safety"):
        path = tmp_path / f"{domain}.json"
        path.write_text(json.dumps(evidence[domain]), encoding="utf-8")
        paths[domain] = str(path)
    loaded = load_domain_reports(paths)
    assert set(loaded["reports"]) == {"provenance", "safety"}
    for domain, path in paths.items():
        assert (
            loaded["sha256"][domain]
            == hashlib.sha256(Path(path).read_bytes()).hexdigest()
        )
