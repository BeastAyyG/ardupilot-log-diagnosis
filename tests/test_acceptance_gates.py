from __future__ import annotations

import hashlib
import json
from pathlib import Path


from synthetic_data.gate_integrity import (
    EVIDENCE_DOMAINS,
    evidence_binding_sha256,
    metrics_bundle_sha256,
)
from synthetic_data.gates import evaluate_acceptance
from synthetic_data.schema import canonical_json_bytes, sha256_bytes


def _full_gate_evidence() -> dict:
    classes = [
        "healthy",
        "vibration_high",
        "motor_imbalance",
        "thrust_loss",
        "gps_quality_poor",
        "compass_interference",
        "power_instability",
        "rc_failsafe",
    ]
    scenarios = classes[1:]
    by_fault = {
        scenario: {"successes": 100, "eligible_runs": 100} for scenario in scenarios
    }
    by_sham = {
        scenario: {"false_manifestations": 0, "eligible_runs": 500}
        for scenario in scenarios
    }
    evidence = {
        "schema": "logdiagnosis.synthetic-acceptance-evidence/v2",
        "candidate": {
            "manifest_sha256": "1" * 64,
            "classifier_sha256": "2" * 64,
            "features_sha256": "3" * 64,
            "labels_sha256": "4" * 64,
            "groups_sha256": "5" * 64,
            "dataset_report_sha256": "6" * 64,
            "split_ledger_sha256": "7" * 64,
            "extraction_contract_sha256": "8" * 64,
            "prediction_ledger_sha256": "9" * 64,
            "code_snapshot_sha256": "a" * 64,
            "dependency_lock_sha256": "b" * 64,
            "declared_classes": classes,
            "required_scenarios": scenarios,
        },
        "source_reports": {
            domain: hashlib.sha256(f"report:{domain}".encode()).hexdigest()
            for domain in EVIDENCE_DOMAINS
        },
        "provenance": {
            "completeness": 1.0,
            "unknown_source_rows": 0,
            "duplicate_or_near_duplicate_clusters": 0,
        },
        "execution": {
            "parameter_readback": {"eligible_runs": 30, "failures": 0},
            "parser": {"successes": 500, "eligible_runs": 500},
            "fault_manifestation": {"by_scenario": by_fault},
            "sham_false_manifestation": {"by_scenario": by_sham},
        },
        "confirmation": {
            "confirmation_cohort_sha256": "c" * 64,
            "blinded": True,
            "candidates_evaluated": 1,
            "use_count": 1,
            "candidate_frozen_before_open": True,
            "classes_frozen_before_open": True,
            "precision_plan_frozen_before_open": True,
            "precision_plan_sha256": "d" * 64,
        },
        "utility": {
            "candidate_macro_f1": 0.82,
            "baseline_macro_f1": 0.75,
            "macro_f1_lower_95": 0.75,
            "per_class_recall_delta_lower_95": {label: 0.0 for label in classes},
            "recall_interval_method": (
                "simultaneous_class_stratified_lineage_bootstrap"
            ),
            "per_class_confirmation_lineages": {label: 30 for label in classes},
            "paired_bootstrap": {
                "lower_95": 0.01,
                "draws": 10000,
                "resampling_unit": "lineage_root_id",
                "stratified_by_declared_class": True,
            },
        },
        "calibration": {
            "top_label_incident_ece_upper_95": 0.05,
            "classwise_incident_ece_upper_95": 0.07,
            "brier_delta_upper_95": -0.01,
            "nll_delta_upper_95": -0.01,
            "every_declared_class_calibrated": True,
            "per_class_real_lineages": {label: 25 for label in classes},
            "method_config_sha256": "e" * 64,
        },
        "safety": {
            "false_critical_rate_upper_95": 0.03,
            "false_critical_increase_upper_95": 0.0,
            "healthy_false_alarm_rate_upper_95": 0.03,
            "severity_aware_end_to_end": True,
        },
        "fidelity": {
            "source_distinguishability_auc": 0.6,
            "source_classifier_permutation_draws": 1000,
            "source_classifier_permutation_p_value": 0.2,
            "conditional_strata_coverage": 1.0,
            "features_outside_real_real_95_envelope": 0.05,
            "raw_temporal_checks_pass": True,
            "raw_temporal_report": {
                "schema": "logdiagnosis.temporal-fidelity/v1",
                "candidate_manifest_sha256": "1" * 64,
                "feature_fidelity_design_sha256": "f" * 64,
                "temporal_design_sha256": "0" * 64,
                "temporal_ledger_sha256": "1" * 64,
                "temporal_method_config_sha256": "2" * 64,
                "dataset": {
                    "features_sha256": "3" * 64,
                    "labels_sha256": "4" * 64,
                    "groups_sha256": "5" * 64,
                    "split_ledger_sha256": "7" * 64,
                },
                "dataset_identity_verified": True,
                "near_duplicate_audit_pass": True,
                "complete": True,
                "raw_temporal_checks_pass": True,
                "required_strata": 1,
                "evaluated_strata": 1,
                "missing_strata": 0,
                "metric_count": 20,
                "bootstrap_draws": 1000,
                "resampling_unit": "lineage_root_id",
                "strata": [{"real_lineages": 12, "synthetic_lineages": 12}],
                "release_authorized": False,
                "accuracy_claim": "not_demonstrated",
            },
            "design_manifest_sha256": "f" * 64,
            "design_required_strata": 12,
            "evaluated_required_strata": 12,
            "missing_required_strata": 0,
            "minimum_units_per_domain_per_stratum": 12,
            "nonlinear_c2st_complete": True,
            "mmd_complete": True,
            "worst_stratum_bounds_pass": True,
            "stratifiers": [
                "primary_label",
                "flight_phase",
                "vehicle_frame",
                "firmware_commit",
                "simulation_family",
            ],
        },
        "ood": {
            "auroc_lower_95": 0.9,
            "detection_at_5pct_id_fpr_lower_95": 0.85,
            "per_domain_lineages": {
                "held_out_firmware": 25,
                "held_out_frame": 25,
                "real_sensor_corruption": 25,
                "unknown_fault_family": 25,
            },
            "minimum_support_complete": True,
            "threshold_reproduced": True,
            "prediction_ledger_sha256": "3" * 64,
            "design_manifest_sha256": "4" * 64,
            "threshold_selection_receipt_sha256": "5" * 64,
            "runtime_ood_threshold_sha256": "6" * 64,
            "runtime_route_evidence_level": "end_to_end_runtime",
            "runtime_action": "abstain_or_route_to_rules_and_review",
            "runtime_abstention_route_test_pass": True,
        },
        "privacy": {
            "direct_identifier_findings": 0,
            "unapproved_absolute_gps_findings": 0,
            "formal_guarantee_claimed": False,
        },
        "reproducibility": {
            "immutable_source_snapshot_sha256": "a" * 64,
            "dependency_lock_sha256": "b" * 64,
            "command_and_rng_receipt_sha256": "1" * 64,
            "independent_repeat_pass": True,
            "independent_repeat_report_sha256": "2" * 64,
        },
    }
    protocol = {
        key: evidence["confirmation"][key]
        for key in (
            "blinded",
            "candidates_evaluated",
            "use_count",
            "candidate_frozen_before_open",
            "classes_frozen_before_open",
            "precision_plan_frozen_before_open",
            "precision_plan_sha256",
        )
    }
    confirmation_report = {
        "schema": "logdiagnosis.confirmation-report/v1",
        "candidate_manifest_sha256": evidence["candidate"]["manifest_sha256"],
        "baseline_manifest_sha256": "f" * 64,
        "confirmation_cohort_sha256": evidence["confirmation"][
            "confirmation_cohort_sha256"
        ],
        "prediction_ledger_sha256": evidence["candidate"][
            "prediction_ledger_sha256"
        ],
        "development_split_ledger_sha256": evidence["candidate"][
            "split_ledger_sha256"
        ],
        "development_groups_sha256": evidence["candidate"]["groups_sha256"],
        "declared_classes": classes,
        "protocol": protocol,
        "cohort_identity_verified": True,
        "physical_lineages_verified": True,
        "development_overlap_count": 0,
        "artifact_overlap_count": 0,
        "near_duplicate_overlap_count": 0,
        "development_lineage_digest_sha256": "1" * 64,
        "cohort_lineage_digest_sha256": "2" * 64,
        "utility": dict(evidence["utility"]),
        "utility_evidence_sha256": sha256_bytes(
            canonical_json_bytes(evidence["utility"])
        ),
        "method_config_sha256": "3" * 64,
        "bootstrap_seed": 20260823,
        "complete": True,
        "derived_from_prediction_ledger": True,
        "independent_authority_required": True,
        "non_promoting": True,
        "release_authorized": False,
        "accuracy_claim": "not_demonstrated_without_gate_and_authority",
    }
    evidence["confirmation"].update(
        {
            "prediction_ledger_sha256": confirmation_report[
                "prediction_ledger_sha256"
            ],
            "confirmation_report_content_sha256": sha256_bytes(
                canonical_json_bytes(confirmation_report)
            ),
            "report": confirmation_report,
        }
    )
    binding = evidence_binding_sha256(evidence)
    evidence["evidence_binding_sha256"] = binding
    for domain in EVIDENCE_DOMAINS:
        evidence[domain]["evidence_binding_sha256"] = binding
    authority_receipt = {
        "receipt_id": "independent-confirmation-001",
        "authority": "independent-test-authority",
        "candidate_manifest_sha256": evidence["candidate"]["manifest_sha256"],
        "confirmation_cohort_sha256": evidence["confirmation"][
            "confirmation_cohort_sha256"
        ],
        "evidence_binding_sha256": binding,
        "metrics_bundle_sha256": metrics_bundle_sha256(evidence),
    }
    evidence["confirmation"]["authority_receipt"] = authority_receipt
    evidence["confirmation"]["authority_receipt_sha256"] = sha256_bytes(
        canonical_json_bytes(authority_receipt)
    )
    return evidence


def test_acceptance_policy_is_executable_and_missing_healthy_safety_blocks() -> None:
    policy = json.loads(
        (
            Path(__file__).parents[1]
            / "synthetic_data"
            / "configs"
            / "acceptance_gates.json"
        ).read_text(encoding="utf-8")
    )
    evidence = _full_gate_evidence()
    policy["evaluation_protocol"]["authorized_confirmation_receipt_sha256"] = [
        evidence["confirmation"]["authority_receipt_sha256"]
    ]
    assert evaluate_acceptance(evidence, policy)["pass"] is True
    evidence["safety"]["healthy_false_alarm_rate_upper_95"] = None
    blocked = evaluate_acceptance(evidence, policy)
    assert blocked["pass"] is False
    assert any(
        gate["gate"] == "healthy_false_alarm_rate" and gate["status"] == "blocked"
        for gate in blocked["gates"]
    )


def test_manual_confirmation_metrics_without_prediction_report_block() -> None:
    policy = json.loads(
        (
            Path(__file__).parents[1]
            / "synthetic_data"
            / "configs"
            / "acceptance_gates.json"
        ).read_text(encoding="utf-8")
    )
    evidence = _full_gate_evidence()
    del evidence["confirmation"]["report"]
    policy["evaluation_protocol"]["authorized_confirmation_receipt_sha256"] = [
        evidence["confirmation"]["authority_receipt_sha256"]
    ]
    result = evaluate_acceptance(evidence, policy)
    envelope = next(
        item
        for item in result["gates"]
        if item["gate"] == "common_candidate_evidence_envelope"
    )
    assert result["pass"] is False
    assert envelope["observed"]["confirmation_prediction_contract"] is False


def test_confirmation_report_cannot_drift_from_utility_domain() -> None:
    policy = json.loads(
        (
            Path(__file__).parents[1]
            / "synthetic_data"
            / "configs"
            / "acceptance_gates.json"
        ).read_text(encoding="utf-8")
    )
    evidence = _full_gate_evidence()
    evidence["confirmation"]["report"]["utility"]["candidate_macro_f1"] = 0.1
    evidence["confirmation"]["confirmation_report_content_sha256"] = sha256_bytes(
        canonical_json_bytes(evidence["confirmation"]["report"])
    )
    result = evaluate_acceptance(evidence, policy)
    envelope = next(
        item
        for item in result["gates"]
        if item["gate"] == "common_candidate_evidence_envelope"
    )
    assert envelope["observed"]["confirmation_prediction_contract"] is False


def test_acceptance_cannot_omit_a_required_scenario_or_declared_class() -> None:
    policy = json.loads(
        (
            Path(__file__).parents[1]
            / "synthetic_data"
            / "configs"
            / "acceptance_gates.json"
        ).read_text(encoding="utf-8")
    )
    evidence = _full_gate_evidence()
    policy["evaluation_protocol"]["authorized_confirmation_receipt_sha256"] = [
        evidence["confirmation"]["authority_receipt_sha256"]
    ]
    del evidence["execution"]["fault_manifestation"]["by_scenario"]["rc_failsafe"]
    del evidence["utility"]["per_class_confirmation_lineages"]["rc_failsafe"]

    result = evaluate_acceptance(evidence, policy)

    assert result["pass"] is False
    blocked = {item["gate"] for item in result["gates"] if item["status"] == "blocked"}
    assert {"fault_manifestation", "confirmation_class_support"} <= blocked


def test_raw_temporal_boolean_cannot_replace_bound_derived_report() -> None:
    policy = json.loads(
        (
            Path(__file__).parents[1]
            / "synthetic_data"
            / "configs"
            / "acceptance_gates.json"
        ).read_text(encoding="utf-8")
    )
    evidence = _full_gate_evidence()
    policy["evaluation_protocol"]["authorized_confirmation_receipt_sha256"] = [
        evidence["confirmation"]["authority_receipt_sha256"]
    ]
    del evidence["fidelity"]["raw_temporal_report"]

    result = evaluate_acceptance(evidence, policy)

    assert result["pass"] is False
    raw_gate = next(
        item for item in result["gates"] if item["gate"] == "raw_temporal_fidelity"
    )
    assert raw_gate["status"] == "blocked"
