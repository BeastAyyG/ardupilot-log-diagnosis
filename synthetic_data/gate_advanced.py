"""Calibration, safety, fidelity, OOD, privacy, and repeatability gates."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .gate_integrity import valid_count, valid_sha256

Recorder = Callable[..., None]


def _nested(payload: dict[str, Any], path: str) -> Any:
    value: Any = payload
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _temporal_fidelity_complete(
    evidence: dict[str, Any], fidelity_policy: dict[str, Any]
) -> bool:
    report = _nested(evidence, "fidelity.raw_temporal_report")
    candidate = evidence.get("candidate")
    if not isinstance(report, dict) or not isinstance(candidate, dict):
        return False
    minimum_support = int(fidelity_policy["minimum_units_per_domain_per_stratum"])
    strata = report.get("strata")
    dataset = report.get("dataset")
    required_hashes = (
        "temporal_design_sha256",
        "temporal_ledger_sha256",
        "temporal_method_config_sha256",
        "feature_fidelity_design_sha256",
    )
    dataset_fields = {
        "features_sha256": "features_sha256",
        "labels_sha256": "labels_sha256",
        "groups_sha256": "groups_sha256",
        "split_ledger_sha256": "split_ledger_sha256",
    }
    return bool(
        report.get("schema") == "logdiagnosis.temporal-fidelity/v1"
        and report.get("candidate_manifest_sha256") == candidate.get("manifest_sha256")
        and report.get("feature_fidelity_design_sha256")
        == _nested(evidence, "fidelity.design_manifest_sha256")
        and all(valid_sha256(report.get(field)) for field in required_hashes)
        and isinstance(dataset, dict)
        and all(
            dataset.get(report_field) == candidate.get(candidate_field)
            for report_field, candidate_field in dataset_fields.items()
        )
        and report.get("dataset_identity_verified") is True
        and report.get("near_duplicate_audit_pass") is True
        and report.get("complete") is True
        and report.get("raw_temporal_checks_pass") is True
        and _nested(evidence, "fidelity.raw_temporal_checks_pass") is True
        and report.get("release_authorized") is False
        and report.get("accuracy_claim") == "not_demonstrated"
        and report.get("missing_strata") == 0
        and valid_count(report.get("required_strata"))
        and report.get("required_strata") > 0
        and report.get("required_strata") == report.get("evaluated_strata")
        and valid_count(report.get("metric_count"))
        and report.get("metric_count") > 0
        and valid_count(report.get("bootstrap_draws"))
        and report.get("bootstrap_draws") >= 1000
        and report.get("resampling_unit") == "lineage_root_id"
        and isinstance(strata, list)
        and len(strata) == report.get("evaluated_strata")
        and all(
            valid_count(row.get("real_lineages"))
            and row.get("real_lineages") >= minimum_support
            and valid_count(row.get("synthetic_lineages"))
            and row.get("synthetic_lineages") >= minimum_support
            for row in strata
            if isinstance(row, dict)
        )
        and all(isinstance(row, dict) for row in strata)
    )


def evaluate_advanced_gates(
    evidence: dict[str, Any],
    policy: dict[str, Any],
    declared_classes: set[str],
    record: Recorder,
    minimum: Recorder,
    maximum: Recorder,
) -> None:
    calibration = policy["calibration"]
    maximum(
        "top_label_incident_ece_upper_bound",
        "calibration.top_label_incident_ece_upper_95",
        float(calibration["maximum_top_label_incident_ece"]),
    )
    maximum(
        "classwise_incident_ece_upper_bound",
        "calibration.classwise_incident_ece_upper_95",
        float(calibration["maximum_classwise_incident_ece"]),
    )
    maximum(
        "brier_noninferiority",
        "calibration.brier_delta_upper_95",
        float(calibration["brier_upper_95_delta_must_not_exceed"]),
    )
    maximum(
        "nll_noninferiority",
        "calibration.nll_delta_upper_95",
        float(calibration["nll_upper_95_delta_must_not_exceed"]),
    )
    calibration_support = _nested(evidence, "calibration.per_class_real_lineages")
    record(
        "calibration_class_coverage",
        isinstance(calibration_support, dict)
        and set(calibration_support) == declared_classes
        and all(
            valid_count(value)
            and value >= int(calibration["minimum_real_lineages_per_class"])
            for value in calibration_support.values()
        )
        and _nested(evidence, "calibration.every_declared_class_calibrated") is True
        and valid_sha256(_nested(evidence, "calibration.method_config_sha256")),
        observed={
            "support": calibration_support,
            "every_class": _nested(
                evidence, "calibration.every_declared_class_calibrated"
            ),
        },
        required=calibration,
    )

    safety = policy["safety"]
    maximum(
        "severity_false_critical_rate",
        "safety.false_critical_rate_upper_95",
        float(safety["maximum_one_sided_95_false_critical_rate"]),
    )
    maximum(
        "false_critical_increase",
        "safety.false_critical_increase_upper_95",
        float(safety["maximum_upper_95_false_critical_increase"]),
    )
    maximum(
        "healthy_false_alarm_rate",
        "safety.healthy_false_alarm_rate_upper_95",
        float(safety["maximum_one_sided_95_healthy_false_alarm_rate"]),
    )
    record(
        "severity_aware_end_to_end_safety",
        _nested(evidence, "safety.severity_aware_end_to_end") is True,
        observed=_nested(evidence, "safety.severity_aware_end_to_end"),
        required=True,
    )

    fidelity = policy["fidelity"]
    maximum(
        "source_distinguishability",
        "fidelity.source_distinguishability_auc",
        float(fidelity["maximum_source_distinguishability_auc"]),
    )
    minimum(
        "source_classifier_permutation_support",
        "fidelity.source_classifier_permutation_draws",
        float(fidelity["minimum_source_classifier_permutation_draws"]),
    )
    minimum(
        "source_classifier_permutation_p_value",
        "fidelity.source_classifier_permutation_p_value",
        float(fidelity["minimum_source_classifier_permutation_p_value"]),
    )
    minimum(
        "conditional_fidelity_coverage",
        "fidelity.conditional_strata_coverage",
        float(fidelity["minimum_conditional_strata_coverage"]),
    )
    maximum(
        "real_real_fidelity_envelope",
        "fidelity.features_outside_real_real_95_envelope",
        float(fidelity["maximum_features_outside_real_real_95_envelope"]),
    )
    record(
        "raw_temporal_fidelity",
        _temporal_fidelity_complete(evidence, fidelity),
        observed=_nested(evidence, "fidelity.raw_temporal_report"),
        required=(
            "machine-derived, candidate/dataset/design-bound raw temporal report "
            "with sufficient independent lineage support"
        ),
    )
    minimum_units = _nested(evidence, "fidelity.minimum_units_per_domain_per_stratum")
    record(
        "fidelity_design_denominator",
        _nested(evidence, "fidelity.missing_required_strata") == 0
        and _nested(evidence, "fidelity.evaluated_required_strata")
        == _nested(evidence, "fidelity.design_required_strata")
        and valid_sha256(_nested(evidence, "fidelity.design_manifest_sha256"))
        and valid_count(minimum_units)
        and minimum_units >= int(fidelity["minimum_units_per_domain_per_stratum"]),
        observed={
            "design": _nested(evidence, "fidelity.design_required_strata"),
            "evaluated": _nested(evidence, "fidelity.evaluated_required_strata"),
            "missing": _nested(evidence, "fidelity.missing_required_strata"),
        },
        required="every preregistered stratum with minimum independent support",
    )
    record(
        "fidelity_test_family",
        _nested(evidence, "fidelity.nonlinear_c2st_complete") is True
        and _nested(evidence, "fidelity.mmd_complete") is True
        and _nested(evidence, "fidelity.worst_stratum_bounds_pass") is True,
        observed=_nested(evidence, "fidelity"),
        required="linear/nonlinear C2ST, MMD, and simultaneous worst-stratum bounds",
    )
    record(
        "fidelity_stratifiers",
        set(_nested(evidence, "fidelity.stratifiers") or [])
        >= set(fidelity["required_stratifiers"]),
        observed=_nested(evidence, "fidelity.stratifiers"),
        required=fidelity["required_stratifiers"],
    )

    ood = policy["ood"]
    minimum("ood_auroc_lower_bound", "ood.auroc_lower_95", float(ood["minimum_auroc"]))
    minimum(
        "ood_detection_at_5pct_id_fpr_lower_bound",
        "ood.detection_at_5pct_id_fpr_lower_95",
        float(ood["minimum_detection_at_5pct_id_fpr"]),
    )
    ood_support = _nested(evidence, "ood.per_domain_lineages")
    record(
        "ood_domain_and_runtime_contract",
        isinstance(ood_support, dict)
        and set(ood_support) == set(ood["required_domains"])
        and all(
            valid_count(value) and value >= int(ood["minimum_lineages_per_domain"])
            for value in ood_support.values()
        )
        and _nested(evidence, "ood.minimum_support_complete") is True
        and _nested(evidence, "ood.threshold_reproduced") is True
        and _nested(evidence, "ood.runtime_abstention_route_test_pass") is True
        and _nested(evidence, "ood.runtime_route_evidence_level")
        == "end_to_end_runtime"
        and _nested(evidence, "ood.runtime_action") == ood["action"]
        and all(
            valid_sha256(_nested(evidence, f"ood.{field}"))
            for field in (
                "prediction_ledger_sha256",
                "design_manifest_sha256",
                "threshold_selection_receipt_sha256",
                "runtime_ood_threshold_sha256",
            )
        ),
        observed={
            "support": ood_support,
            "runtime_route": _nested(
                evidence, "ood.runtime_abstention_route_test_pass"
            ),
            "runtime_evidence_level": _nested(
                evidence, "ood.runtime_route_evidence_level"
            ),
            "threshold_reproduced": _nested(evidence, "ood.threshold_reproduced"),
        },
        required=ood,
    )

    privacy = policy["privacy"]
    maximum(
        "direct_identifier_findings",
        "privacy.direct_identifier_findings",
        float(privacy["maximum_direct_identifier_findings"]),
    )
    maximum(
        "unapproved_absolute_gps_findings",
        "privacy.unapproved_absolute_gps_findings",
        float(privacy["maximum_unapproved_absolute_gps_findings"]),
    )
    record(
        "privacy_claim_honesty",
        _nested(evidence, "privacy.formal_guarantee_claimed") is not True
        or _nested(evidence, "privacy.formal_guarantee_proven") is True,
        observed=_nested(evidence, "privacy"),
        required="no formal guarantee claim without proof",
    )

    candidate = evidence["candidate"]
    reproducibility_checks = {
        "immutable_source_snapshot": _nested(
            evidence, "reproducibility.immutable_source_snapshot_sha256"
        )
        == candidate.get("code_snapshot_sha256"),
        "dependency_lock": _nested(evidence, "reproducibility.dependency_lock_sha256")
        == candidate.get("dependency_lock_sha256"),
        "command_and_rng_receipt": valid_sha256(
            _nested(evidence, "reproducibility.command_and_rng_receipt_sha256")
        ),
        "independent_repeat": _nested(
            evidence, "reproducibility.independent_repeat_pass"
        )
        is True
        and valid_sha256(
            _nested(evidence, "reproducibility.independent_repeat_report_sha256")
        ),
    }
    record(
        "reproducibility",
        all(reproducibility_checks.values()),
        observed=reproducibility_checks,
        required=policy["reproducibility"],
    )
