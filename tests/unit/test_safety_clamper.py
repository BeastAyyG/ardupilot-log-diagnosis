from src.core.remediation.safety_clamper import clamp_parameter_changes


def test_safety_clamper_limits_numeric_delta_and_emits_packets():
    result = clamp_parameter_changes({"ATC_RAT_RLL_P": 100.0, "ZERO": 0.0}, {"ATC_RAT_RLL_P": 150.0, "ZERO": 1.0})

    assert result.changes[0].clamped == 125.0
    assert result.changes[0].was_clamped
    assert result.changes[1].clamped == 0.0
    assert result.mavlink_packets[0]["command"] == "PARAM_SET"
    assert result.param_lines[0] == "ATC_RAT_RLL_P,125"
