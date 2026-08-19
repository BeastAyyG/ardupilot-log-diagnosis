from src.comparison.trend_analyzer import TrendAnalyzer


def test_trend_report_has_quality_gate_and_accepts_feature_payloads(tmp_path):
    def flight(name, firmware):
        return {
            "metadata": {
                "filename": name,
                "duration_sec": 10,
                "vehicle_type": "Copter",
                "firmware": firmware,
                "log_file": str(tmp_path / name),
            },
            "features": {
                "vibe_x_mean": 1,
                "vibe_y_mean": 1,
                "vibe_z_mean": 2,
                "vibe_clip_total": 0,
                "mag_field_range": 10,
                "bat_volt_min": 15,
                "bat_curr_max": 10,
                "ekf_vel_var_max": 0.1,
                "ekf_pos_var_max": 0.1,
                "motor_spread_max": 20,
                "gps_hdop_max": 1,
            },
            "diagnoses": [],
        }
    report = TrendAnalyzer(cache_dir=tmp_path).compare_flights([flight("a.bin", "4.5"), flight("b.bin", "4.5")])
    assert report["schema_version"] == "trend-report.v2"
    assert report["comparison_quality"]["comparable"] is True
    assert report["flights_analyzed"] == 2


def test_trend_report_does_not_mark_zero_change_as_critical(tmp_path):
    flight = {
        "metadata": {"filename": "same.bin", "duration_sec": 10, "vehicle_type": "Copter", "firmware": "4.5"},
        "features": {"vibe_z_mean": 2.0, "bat_volt_min": 15.0},
        "diagnoses": [],
    }
    report = TrendAnalyzer(cache_dir=tmp_path).compare_flights([flight, flight])

    assert not report["insights"]
    assert "CRITICAL" not in report["summary"]
