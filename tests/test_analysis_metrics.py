from src.analysis.flight_phases import segment_flight
from src.analysis.sensor_metrics import analyze_sensors
from src.analysis.tuning_metrics import analyze_tuning
from src.analysis.health_score import calculate_health_score


def _parsed():
    timestamps = [i * 100_000 for i in range(32)]
    return {
        "metadata": {"vehicle_type": "Copter"},
        "messages": {
            "RATE": [
                {"TimeUS": t, "RDes": 10.0 if i >= 8 else 0.0, "R": 9.0 if i >= 8 else 0.0,
                 "PDes": 0.0, "P": 0.0, "YDes": 0.0, "Y": 0.0}
                for i, t in enumerate(timestamps)
            ],
            "IMU": [
                {"TimeUS": t, "AccX": 1.0 + (i % 4) / 10.0, "AccY": 0.2, "AccZ": 2.0}
                for i, t in enumerate(timestamps)
            ],
            "BAT": [{"TimeUS": t, "Volt": 16.8 - i / 100.0, "Curr": 10 + i} for i, t in enumerate(timestamps)],
            "MAG": [{"TimeUS": t, "MagX": 200, "MagY": 0, "MagZ": 0} for t in timestamps],
            "GPS": [{"TimeUS": t, "HDop": 0.8, "NSats": 15, "Status": 3} for t in timestamps],
        },
        "parameters": {"BATT_CELLS": 4, "INS_GYRO_FILTER": 40},
        "mode_changes": [
            {"time_us": 0, "mode_name": "Stabilize", "reason": 0},
            {"time_us": 1_600_000, "mode_name": "RTL", "reason": 1},
        ],
        "parameter_changes": [],
        "errors": [],
        "events": [],
        "status_messages": [],
    }


def test_phase_segmentation():
    result = segment_flight(_parsed())
    assert result["status"] == "reliable"
    assert result["segments"][1]["phase"] == "recovery"


def test_sensor_metrics_are_presence_gated():
    result = analyze_sensors(_parsed())
    assert result["battery"]["estimated_cell_count"] == 4
    assert result["gps"]["fix_rate"] == 1.0
    assert result["compass"]["field_norm"]["status"] == "reliable"
    empty = analyze_sensors({"messages": {}, "parameters": {}})
    assert empty["gps"]["status"] == "insufficient_data"


def test_tuning_metrics_are_safe_and_read_only():
    result = analyze_tuning(_parsed())
    assert result["write_parameters"] is False
    assert result["pid"]["roll"]["status"] in {"reliable", "degraded"}
    assert result["vibration_fft"]["x"]["status"] == "reliable"


def test_health_score_does_not_call_generic_logs_healthy_when_root_cause_is_unsupported():
    result = calculate_health_score(
        diagnoses=[],
        quality_report={
            "overall_status": "RELIABLE",
            "input_format": {"format": "px4_ulog"},
        },
    )
    assert result["status"] == "degraded"
    # The 25-point unsupported-format penalty puts the score in the explicit
    # review band (75), while status remains degraded to block a healthy claim.
    assert result["label"] == "review"
    assert result["score"] == 75.0
    assert "unsupported" in result["quality_reason"]
