from src.diagnosis.parameter_validation import validate_parameters


def test_parameter_validation_flags_default_pid_with_oscillation():
    warnings = validate_parameters(
        {"ATC_RAT_RLL_P": 0.135},
        {"vibe_z_max": 35.0, "att_roll_std": 9.0},
        "Copter",
    )
    assert warnings
    assert "ATC_RAT_RLL_P" in warnings[0]["message"]


def test_parameter_validation_skips_non_copter():
    warnings = validate_parameters(
        {"ATC_RAT_RLL_P": 0.135},
        {"vibe_z_max": 35.0, "att_roll_std": 9.0},
        "Rover",
    )
    assert warnings == []
