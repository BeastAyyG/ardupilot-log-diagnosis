from src.cli.formatter import DiagnosisFormatter


def test_hypothesis_onset_is_relative_to_log_start():
    output = DiagnosisFormatter().format_terminal(
        diagnoses=[],
        metadata={
            "log_file": "flight.BIN",
            "duration_sec": 20.0,
            "first_time_us": 360_000_000,
        },
        explain_data={
            "hypotheses": [
                {
                    "failure_type": "compass_interference",
                    "merged_confidence": 0.8,
                    "source": "rule",
                    "lead_feature": "mag_field_range",
                    "tanomaly": 364_000_000,
                }
            ],
            "causal_arbiter": {},
        },
    )

    assert "T+4.0s" in output
    assert "T+364.0s" not in output


def test_temporal_root_cause_and_strongest_finding_are_distinguished():
    diagnoses = [
        {
            "failure_type": "vibration_high",
            "confidence": 0.59,
            "severity": "warning",
            "detection_method": "rule",
            "evidence": [],
            "recommendation": "Inspect mounts.",
            "reason_code": "uncertain",
        },
        {
            "failure_type": "power_instability",
            "confidence": 0.79,
            "severity": "critical",
            "detection_method": "ml",
            "evidence": [],
            "recommendation": "Inspect power.",
            "reason_code": "confirmed",
        },
    ]
    decision = {
        "status": "uncertain",
        "requires_human_review": True,
        "top_guess": "vibration_high",
        "top_confidence": 0.59,
        "rationale": [],
        "ranked_subsystems": [],
    }

    output = DiagnosisFormatter().format_terminal(
        diagnoses=diagnoses,
        metadata={"log_file": "flight.BIN", "duration_sec": 20.0},
        decision=decision,
        explain_data={
            "hypotheses": [],
            "causal_arbiter": {"selected_failure_type": "vibration_high"},
        },
    )

    assert "Likely Root Cause: VIBRATION_HIGH (59%)" in output
    assert "Highest-Confidence Finding: POWER_INSTABILITY (79%)" in output
