"""Fail-closed evaluator for synthetic-data confirmation evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scipy.stats import beta

from .contracts import validate_contract
from .gate_advanced import evaluate_advanced_gates
from .gate_integrity import (
    envelope_checks,
    valid_count,
    valid_number,
    valid_rate,
    valid_sha256,
)
from .schema import sha256_file

GATE_SCHEMA = "logdiagnosis.synthetic-gate-evaluation/v2"
POLICY_SCHEMA = "logdiagnosis.synthetic-acceptance-gates/v3"


def _nested(payload: dict[str, Any], path: str) -> Any:
    value: Any = payload
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _one_sided_lower(successes: int, total: int, confidence: float) -> float:
    if total <= 0 or successes < 0 or successes > total:
        raise ValueError("invalid binomial support")
    if successes == 0:
        return 0.0
    return float(beta.ppf(1.0 - confidence, successes, total - successes + 1))


def _one_sided_upper(events: int, total: int, confidence: float) -> float:
    if total <= 0 or events < 0 or events > total:
        raise ValueError("invalid binomial support")
    if events == total:
        return 1.0
    return float(beta.ppf(confidence, events + 1, total - events))


def evaluate_acceptance(
    evidence: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    if policy.get("schema") != POLICY_SCHEMA:
        raise ValueError("acceptance policy schema is unsupported")
    validate_contract(evidence, "acceptance_evidence.schema.json")
    confidence_value = policy.get("confidence_level")
    if not valid_rate(confidence_value) or not 0.5 < float(confidence_value) < 1.0:
        raise ValueError("confidence_level must be finite and between 0.5 and 1")
    confidence = float(confidence_value)
    gates: list[dict[str, Any]] = []

    def record(
        name: str,
        passed: bool,
        *,
        observed: Any,
        required: Any,
        reason: str = "",
    ) -> None:
        gates.append(
            {
                "gate": name,
                "status": "pass" if passed else "blocked",
                "observed": observed,
                "required": required,
                "reason": reason
                if reason
                else ("satisfied" if passed else "not satisfied"),
            }
        )

    def maximum(name: str, path: str, threshold: float) -> None:
        value = _nested(evidence, path)
        passed = valid_number(value) and float(value) <= threshold
        record(
            name,
            passed,
            observed=value,
            required=f"<= {threshold}",
            reason="missing metric" if value is None else "",
        )

    def minimum(name: str, path: str, threshold: float) -> None:
        value = _nested(evidence, path)
        passed = valid_number(value) and float(value) >= threshold
        record(
            name,
            passed,
            observed=value,
            required=f">= {threshold}",
            reason="missing metric" if value is None else "",
        )

    envelope = envelope_checks(evidence, policy)
    record(
        "common_candidate_evidence_envelope",
        all(
            value is True
            for key, value in envelope.items()
            if not key.startswith("computed_")
        ),
        observed=envelope,
        required="schema-valid, common-bound reports and allowlisted confirmation authority",
    )

    integrity = policy["integrity"]
    minimum(
        "provenance_completeness",
        "provenance.completeness",
        float(integrity["provenance_completeness"]),
    )
    maximum(
        "unknown_source_rows",
        "provenance.unknown_source_rows",
        float(integrity["maximum_unknown_source_rows"]),
    )
    maximum(
        "duplicate_or_near_duplicate_clusters",
        "provenance.duplicate_or_near_duplicate_clusters",
        float(integrity["maximum_duplicate_or_near_duplicate_clusters"]),
    )
    readback_runs = _nested(evidence, "execution.parameter_readback.eligible_runs")
    readback_failures = _nested(evidence, "execution.parameter_readback.failures")
    readback_pass = bool(
        valid_count(readback_runs)
        and valid_count(readback_failures)
        and readback_runs >= int(integrity["minimum_parameter_readback_runs"])
        and readback_failures == 0
    )
    record(
        "parameter_readback",
        readback_pass,
        observed={"eligible_runs": readback_runs, "failures": readback_failures},
        required={
            "minimum_runs": integrity["minimum_parameter_readback_runs"],
            "failures": 0,
        },
    )

    parser_policy = integrity["parser_success"]
    parser_successes = _nested(evidence, "execution.parser.successes")
    parser_total = _nested(evidence, "execution.parser.eligible_runs")
    parser_lower = None
    if (
        valid_count(parser_successes)
        and valid_count(parser_total)
        and parser_successes <= parser_total
    ):
        parser_lower = _one_sided_lower(parser_successes, parser_total, confidence)
    parser_pass = bool(
        parser_lower is not None
        and parser_total >= int(parser_policy["minimum_eligible_runs"])
        and parser_lower >= float(parser_policy["minimum_one_sided_95_lower_rate"])
    )
    record(
        "parser_success",
        parser_pass,
        observed={"eligible_runs": parser_total, "lower_bound": parser_lower},
        required=parser_policy,
    )

    for evidence_key, policy_key, event_key, direction in (
        ("fault_manifestation", "fault_manifestation", "successes", "lower"),
        (
            "sham_false_manifestation",
            "sham_false_manifestation",
            "false_manifestations",
            "upper",
        ),
    ):
        scenario_evidence = _nested(evidence, f"execution.{evidence_key}.by_scenario")
        scenario_policy = integrity[policy_key]
        required_scenarios = set(policy["evaluation_protocol"]["required_scenarios"])
        scenario_results: dict[str, Any] = {}
        all_pass = bool(
            isinstance(scenario_evidence, dict)
            and set(scenario_evidence) == required_scenarios
        )
        if isinstance(scenario_evidence, dict):
            for scenario, values in sorted(scenario_evidence.items()):
                total = (
                    values.get("eligible_runs") if isinstance(values, dict) else None
                )
                events = values.get(event_key) if isinstance(values, dict) else None
                bound = None
                passed = False
                if valid_count(total) and valid_count(events) and events <= total:
                    if direction == "lower":
                        bound = _one_sided_lower(events, total, confidence)
                        passed = bool(
                            total
                            >= int(
                                scenario_policy["minimum_eligible_runs_per_scenario"]
                            )
                            and bound
                            >= float(scenario_policy["minimum_one_sided_95_lower_rate"])
                        )
                    else:
                        bound = _one_sided_upper(events, total, confidence)
                        passed = bool(
                            total
                            >= int(
                                scenario_policy["minimum_eligible_runs_per_scenario"]
                            )
                            and bound
                            <= float(scenario_policy["maximum_one_sided_95_upper_rate"])
                        )
                scenario_results[scenario] = {
                    "eligible_runs": total,
                    "bound": bound,
                    "pass": passed,
                }
                all_pass = all_pass and passed
        record(
            evidence_key,
            bool(all_pass),
            observed=scenario_results or scenario_evidence,
            required=scenario_policy,
        )

    protocol = policy["evaluation_protocol"]
    protocol_checks = {
        "blinded": _nested(evidence, "confirmation.blinded") is True,
        "one_candidate": _nested(evidence, "confirmation.candidates_evaluated") == 1,
        "one_use": _nested(evidence, "confirmation.use_count") == 1,
        "candidate_frozen": _nested(
            evidence, "confirmation.candidate_frozen_before_open"
        )
        is True,
        "classes_frozen": _nested(evidence, "confirmation.classes_frozen_before_open")
        is True,
    }
    record(
        "independent_confirmation_protocol",
        all(protocol_checks.values()),
        observed=protocol_checks,
        required=protocol,
    )
    support = _nested(evidence, "utility.per_class_confirmation_lineages")
    minimum_support = int(protocol["minimum_confirmation_lineages_per_class"])
    declared_classes = set(protocol["declared_classes"])
    support_pass = bool(
        isinstance(support, dict)
        and set(support) == declared_classes
        and all(
            valid_count(value) and value >= minimum_support
            for value in support.values()
        )
    )
    record(
        "confirmation_class_support",
        support_pass,
        observed=support,
        required=f">= {minimum_support} independent lineages per declared class",
    )
    record(
        "confirmation_precision_plan",
        _nested(evidence, "confirmation.precision_plan_frozen_before_open") is True
        and valid_sha256(_nested(evidence, "confirmation.precision_plan_sha256")),
        observed={
            "frozen": _nested(
                evidence, "confirmation.precision_plan_frozen_before_open"
            ),
            "sha256": _nested(evidence, "confirmation.precision_plan_sha256"),
        },
        required="hash-bound precision/power plan frozen before confirmation",
    )

    utility = policy["utility"]
    minimum(
        "absolute_macro_f1_lower_bound",
        "utility.macro_f1_lower_95",
        float(utility["minimum_macro_f1_lower_95"]),
    )
    delta_lower = _nested(evidence, "utility.paired_bootstrap.lower_95")
    delta_threshold = float(utility["minimum_lower_95_macro_f1_delta"])
    record(
        "paired_macro_f1_delta_lower_bound",
        valid_number(delta_lower) and float(delta_lower) > delta_threshold,
        observed=delta_lower,
        required=f"> {delta_threshold}",
        reason="missing metric" if delta_lower is None else "",
    )
    minimum(
        "paired_bootstrap_draws",
        "utility.paired_bootstrap.draws",
        float(utility["paired_bootstrap_draws"]),
    )
    record(
        "paired_bootstrap_contract",
        _nested(evidence, "utility.paired_bootstrap.resampling_unit")
        == utility["bootstrap_unit"]
        and _nested(evidence, "utility.paired_bootstrap.stratified_by_declared_class")
        == utility["bootstrap_stratified_by_class"],
        observed=_nested(evidence, "utility.paired_bootstrap"),
        required={
            "unit": utility["bootstrap_unit"],
            "stratified": utility["bootstrap_stratified_by_class"],
        },
    )
    recall_bounds = _nested(evidence, "utility.per_class_recall_delta_lower_95")
    minimum_recall_delta = float(utility["minimum_per_class_recall_delta_lower_95"])
    record(
        "simultaneous_per_class_recall_noninferiority",
        isinstance(recall_bounds, dict)
        and set(recall_bounds) == declared_classes
        and all(
            valid_number(value) and float(value) >= minimum_recall_delta
            for value in recall_bounds.values()
        )
        and _nested(evidence, "utility.recall_interval_method")
        == utility["recall_interval_method"],
        observed=recall_bounds,
        required={
            "each_lower_95": f">= {minimum_recall_delta}",
            "method": utility["recall_interval_method"],
        },
    )

    evaluate_advanced_gates(
        evidence,
        policy,
        declared_classes,
        record,
        minimum,
        maximum,
    )

    blocked = [item for item in gates if item["status"] != "pass"]
    return {
        "schema": GATE_SCHEMA,
        "policy_schema": POLICY_SCHEMA,
        "pass": not blocked,
        "release_authorized": False,
        "non_promoting": True,
        "blocked_gate_count": len(blocked),
        "gates": gates,
        "accuracy_claim": "supported_for_independent_review"
        if not blocked
        else "not_demonstrated",
    }


def evaluate_files(
    evidence_path: str | Path,
    policy_path: str | Path,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    evidence = json.loads(Path(evidence_path).read_text(encoding="utf-8"))
    policy = json.loads(Path(policy_path).read_text(encoding="utf-8"))
    if not isinstance(evidence, dict) or not isinstance(policy, dict):
        raise ValueError("evidence and policy roots must be JSON objects")
    report = evaluate_acceptance(evidence, policy)
    report["evidence_sha256"] = sha256_file(evidence_path)
    report["policy_sha256"] = sha256_file(policy_path)
    if output_path:
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report
