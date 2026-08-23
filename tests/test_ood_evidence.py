from __future__ import annotations

import json

import pytest

from synthetic_data.ood import build_ood_report, threshold_config_sha256

DOMAINS = [
    "held_out_firmware",
    "held_out_frame",
    "real_sensor_corruption",
    "unknown_fault_family",
]


def _write_inputs(
    tmp_path, *, broken_route: bool = False, missing_domain: bool = False
):
    design = {
        "schema": "logdiagnosis.ood-evaluation-design/v1",
        "candidate_manifest_sha256": "a" * 64,
        "confirmation_cohort_sha256": "b" * 64,
        "required_domains": DOMAINS,
        "minimum_lineages_per_domain": 20,
        "minimum_id_threshold_lineages": 20,
        "minimum_id_evaluation_lineages": 20,
        "id_false_positive_rate_target": 0.05,
        "frozen_threshold": 0.2,
        "threshold_selection_receipt_sha256": "c" * 64,
        "frozen_before_evaluation": True,
        "bootstrap_draws": 1000,
        "confidence_level": 0.95,
        "random_seed": 77,
        "runtime_action": "abstain_or_route_to_rules_and_review",
    }
    threshold_hash = threshold_config_sha256(design)
    records = []
    for index in range(24):
        score = 0.2 if index >= 22 else 0.01 + index * (0.17 / 21)
        records.append(
            {
                "lineage_root_id": f"id-cal-{index}",
                "role": "id_threshold_calibration",
                "ood_domain": "in_distribution",
                "ood_score": score,
                "near_duplicate_cluster_id": "",
            }
        )
    for index in range(24):
        records.append(
            {
                "lineage_root_id": f"id-eval-{index}",
                "role": "id_evaluation",
                "ood_domain": "in_distribution",
                "ood_score": 0.01 + index * (0.18 / 23),
                "near_duplicate_cluster_id": "",
                "runtime_ood_threshold_sha256": threshold_hash,
                "runtime_requires_human_review": False,
                "runtime_action": "normal_diagnosis",
            }
        )
    produced_domains = DOMAINS[:-1] if missing_domain else DOMAINS
    for domain_index, domain in enumerate(produced_domains):
        for index in range(24):
            records.append(
                {
                    "lineage_root_id": f"ood-{domain_index}-{index}",
                    "role": "ood_evaluation",
                    "ood_domain": domain,
                    "ood_score": 0.80 + index * 0.001,
                    "near_duplicate_cluster_id": "",
                    "runtime_ood_threshold_sha256": threshold_hash,
                    "runtime_requires_human_review": not (
                        broken_route and domain_index == 0 and index == 0
                    ),
                    "runtime_action": "abstain_or_route_to_rules_and_review",
                }
            )
    ledger = {
        "schema": "logdiagnosis.ood-prediction-ledger/v1",
        "candidate_manifest_sha256": "a" * 64,
        "confirmation_cohort_sha256": "b" * 64,
        "score_method_config_sha256": "d" * 64,
        "runtime_route_evidence_level": "end_to_end_runtime",
        "records": records,
    }
    design_path = tmp_path / "ood_design.json"
    ledger_path = tmp_path / "ood_ledger.json"
    design_path.write_text(json.dumps(design), encoding="utf-8")
    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
    return ledger_path, design_path


def test_ood_report_computes_lineage_bootstrap_and_runtime_route(tmp_path) -> None:
    ledger, design = _write_inputs(tmp_path)

    report = build_ood_report(ledger, design)

    assert report["gate_ready"] is True
    assert report["auroc_lower_95"] == pytest.approx(1.0)
    assert report["detection_at_5pct_id_fpr_lower_95"] == 1.0
    assert report["runtime_abstention_route_test_pass"] is True
    assert report["per_domain_lineages"] == {domain: 24 for domain in DOMAINS}


def test_ood_runtime_route_failure_is_machine_derived(tmp_path) -> None:
    ledger, design = _write_inputs(tmp_path, broken_route=True)

    report = build_ood_report(ledger, design)

    assert report["runtime_abstention_route_test_pass"] is False
    assert report["gate_ready"] is False


def test_ood_missing_preregistered_domain_blocks_metrics(tmp_path) -> None:
    ledger, design = _write_inputs(tmp_path, missing_domain=True)

    report = build_ood_report(ledger, design)

    assert report["per_domain_lineages"]["unknown_fault_family"] == 0
    assert report["minimum_support_complete"] is False
    assert report["gate_ready"] is False


def test_ood_near_duplicate_cluster_cannot_cross_units(tmp_path) -> None:
    ledger_path, design_path = _write_inputs(tmp_path)
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger["records"][0]["near_duplicate_cluster_id"] = "duplicate-1"
    ledger["records"][1]["near_duplicate_cluster_id"] = "duplicate-1"
    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")

    with pytest.raises(ValueError, match="near-duplicate"):
        build_ood_report(ledger_path, design_path)
