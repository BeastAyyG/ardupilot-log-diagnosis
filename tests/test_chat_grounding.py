from src.chat.assistant import ChatAssistant


def _quality(status: str, capability: str, missing: list[str]) -> dict:
    return {
        "overall_status": status,
        "capabilities": {
            capability: {
                "status": "UNSUPPORTED",
                "missing_messages": missing,
                "recommendation": "Capture the required telemetry on the next flight.",
            }
        },
    }


def test_chat_does_not_call_missing_vibration_telemetry_normal():
    result = {
        "schema_version": "analysis-response.v1",
        "features": {"vibe_z_mean": 0.0, "vibe_clip_total": 0.0},
        "hardware_report": {
            "log_quality": _quality("UNSUPPORTED", "vibration_analysis", ["VIBE", "IMU"])
        },
    }
    answer = ChatAssistant().ask("Is vibration normal?", result)
    assert "cannot be assessed" in answer["answer"]
    assert "NORMAL" not in answer["answer"]
    assert answer["confidence"] <= 0.25


def test_chat_caps_answers_for_degraded_input():
    result = {
        "schema_version": "analysis-response.v1",
        "features": {"gps_hdop_max": 1.1},
        "hardware_report": {
            "log_quality": {
                "overall_status": "DEGRADED",
                "capabilities": {
                    "compass_gps_navigation": {
                        "status": "RELIABLE",
                        "missing_messages": [],
                    }
                },
            }
        },
    }
    answer = ChatAssistant().ask("Is GPS quality good?", result)
    assert answer["confidence"] <= 0.55
    assert "human review" in answer["answer"]
