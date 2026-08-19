from src.analysis.control_metrics import analyze_control


def test_control_metrics_reports_tracking_and_saturation():
    parsed = {
        "messages": {
            "ATT": [
                {"Roll": 2, "DesRoll": 5, "Pitch": 0, "DesPitch": 1},
                {"Roll": 4, "DesRoll": 5, "Pitch": 2, "DesPitch": 1},
            ],
            "RATE": [
                {"RDes": 10, "R": 8, "PDes": 2, "P": 2, "YDes": 0, "Y": 0},
                {"RDes": 10, "R": 9, "PDes": 2, "P": 1, "YDes": 0, "Y": 0},
            ],
            "RCOU": [{"C1": 2000, "C2": 1500}, {"C1": 1500, "C2": 1500}],
            "CTUN": [{"ThO": 0.8}],
        }
    }
    result = analyze_control(parsed)
    assert result["attitude_tracking"]["roll_error"]["count"] == 2
    assert result["rate_tracking"]["roll"]["status"] == "reliable"
    assert result["actuator_authority"]["saturation_rate"] == 0.5

