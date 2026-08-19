from src.core.reasoning.rule_matrix_44 import RULE_MATRIX_44, evaluate_rule_matrix


def test_rule_matrix_has_44_source_bound_checks():
    assert len(RULE_MATRIX_44) == 44
    assert all(rule.documentation_url.startswith("https://ardupilot.org/") for rule in RULE_MATRIX_44)


def test_rule_matrix_evaluates_deterministically_and_ignores_missing_features():
    findings = evaluate_rule_matrix({"vibe_z_max": 42.0, "failsafe_event_count": 1, "unknown": 999})

    assert [finding.rule_id for finding in findings] == ["S04", "F03"]
    assert all(finding.documentation_url for finding in findings)
