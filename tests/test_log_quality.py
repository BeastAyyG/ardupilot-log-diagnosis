from src.diagnosis.log_quality import LogQualityEngine


def test_log_quality_reliable():
    parsed_log = {
        "metadata": {
            "duration_sec": 60.0,
            "total_messages": 10000,
            "message_types": {
                "VIBE": 1200,    # 20 Hz
                "IMU": 3000,     # 50 Hz
                "GPS": 300,      # 5 Hz
                "MAG": 300,      # 5 Hz
                "BAT": 120,      # 2 Hz
                "XKF4": 300,     # 5 Hz
                "RCOU": 600,     # 10 Hz
                "ATT": 1200,     # 20 Hz
                "RATE": 1200,    # 20 Hz
                "EV": 5,
            }
        }
    }
    engine = LogQualityEngine()
    report = engine.evaluate(parsed_log)
    assert report["overall_status"] == "RELIABLE"
    assert report["capabilities"]["vibration_analysis"]["status"] == "RELIABLE"
    assert report["capabilities"]["compass_gps_navigation"]["status"] == "RELIABLE"
    assert len(report["actionable_recommendations"]) == 0


def test_log_quality_degraded_and_unsupported():
    parsed_log = {
        "metadata": {
            "duration_sec": 60.0,
            "total_messages": 1000,
            "message_types": {
                # Missing VIBE and IMU completely -> vibration_analysis UNSUPPORTED
                "GPS": 300,
                "MAG": 300,
                # Missing BAT -> power UNSUPPORTED
                "ATT": 600,      # 10 Hz
                "RCOU": 60,      # 1 Hz (degraded)
            }
        }
    }
    engine = LogQualityEngine()
    report = engine.evaluate(parsed_log)
    assert report["overall_status"] in ("DEGRADED", "UNSUPPORTED")
    assert report["capabilities"]["vibration_analysis"]["status"] == "UNSUPPORTED"
    assert "830847" in report["capabilities"]["vibration_analysis"]["recommendation"]
    assert report["capabilities"]["power_battery_dynamics"]["status"] == "UNSUPPORTED"


def test_log_quality_derives_message_counts_when_metadata_is_minimal():
    report = LogQualityEngine().evaluate(
        {
            "metadata": {"duration_sec": 1.0},
            "messages": {"GPS": [{"TimeUS": 0}], "ATT": [{"TimeUS": 0}]},
        }
    )
    assert report["total_messages"] == 2
    assert report["capabilities"]["compass_gps_navigation"]["status"] == "DEGRADED"
    assert len(report["actionable_recommendations"]) >= 2
