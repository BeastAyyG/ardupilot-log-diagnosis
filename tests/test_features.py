import math

from src.features.pipeline import FeaturePipeline
from src.constants import FEATURE_NAMES

def test_all_features_numerical():
    pipeline = FeaturePipeline()
    # Mocking parsed log
    parsed_mock = {"messages": {}, "metadata": {"filepath": "test.BIN"}}
    features = pipeline.extract(parsed_mock)
    
    for k, v in features.items():
        if not k.startswith("_"):
            assert isinstance(v, (int, float))
            assert math.isfinite(v)


def test_pipeline_sanitizes_non_finite_parser_values():
    pipeline = FeaturePipeline()
    features = pipeline.extract(
        {
            "messages": {
                "BAT": [{"Volt": float("nan"), "Curr": float("inf")}],
                "POWR": [{"Vcc": float("nan"), "VServo": float("inf")}],
            }
        }
    )

    assert all(math.isfinite(value) for key, value in features.items() if not key.startswith("_"))
            
def test_feature_names_consistent():
    pipeline = FeaturePipeline()
    extracted_keys = [k for k in pipeline.extract({}).keys() if not k.startswith("_")]
    assert set(extracted_keys) == set(pipeline.get_feature_names())
    
def test_missing_messages():
    pipeline = FeaturePipeline()
    features = pipeline.extract({"messages": {}})
    for k, v in features.items():
        if not k.startswith("_"):
            assert v == 0.0

def test_vibration_extraction():
    pipeline = FeaturePipeline()
    vibe_msg = {
        "VibeX": 10.0, "VibeY": 20.0, "VibeZ": 30.0,
        "Clip0": 1, "Clip1": 0, "Clip2": 2
    }
    parsed = {"messages": {"VIBE": [vibe_msg]}}
    features = pipeline.extract(parsed)
    assert features["vibe_x_mean"] == 10.0
    assert features["vibe_z_max"] == 30.0
    assert features["vibe_clip_total"] == 3.0

def test_ekf_extraction():
    pipeline = FeaturePipeline()
    nkf4_msg = {"SV": 0.5, "SP": 0.2, "SH": 0.1, "SM": 0.0, "PI": 1, "SS": 1}
    parsed = {"messages": {"NKF4": [nkf4_msg, nkf4_msg]}}
    features = pipeline.extract(parsed)
    assert features["ekf_vel_var_mean"] == 0.5
    assert features["ekf_pos_var_mean"] == 0.2
    assert features["ekf_flags_error_pct"] == 1.0

def test_pipeline_integration():
    pipeline = FeaturePipeline()
    features = pipeline.extract({"messages": {}})
    assert "_metadata" in features
    
def test_feature_count():
    pipeline = FeaturePipeline()
    assert len(pipeline.get_feature_names()) == len(FEATURE_NAMES)
    assert set(pipeline.get_feature_names()) == set(FEATURE_NAMES)


def test_power_load_features_capture_sag_and_spikes():
    pipeline = FeaturePipeline()
    parsed = {
        "messages": {
            "BAT": [
                {"TimeUS": 0, "Volt": 16.8, "Curr": 10.0},
                {"TimeUS": 1_000_000, "Volt": 15.0, "Curr": 40.0},
                {"TimeUS": 2_000_000, "Volt": 16.5, "Curr": 11.0},
            ]
        },
        "parameters": {"BATT_LOW_VOLT": 15.5},
    }
    features = pipeline.extract(parsed)
    assert features["bat_power_max"] == 600.0
    assert features["bat_sag_per_amp"] > 0.0
    assert features["bat_low_voltage_pct"] > 0.0
    assert features["bat_current_spike_pct"] > 0.0


def test_pid_rate_features_capture_tracking_error_and_oscillation():
    pipeline = FeaturePipeline()
    parsed = {
        "messages": {
            "RATE": [
                {"RDes": 10.0, "R": 0.0},
                {"RDes": 0.0, "R": 10.0},
                {"RDes": 10.0, "R": 0.0},
            ]
        }
    }
    features = pipeline.extract(parsed)
    assert features["pid_rate_err_max"] == 10.0
    assert features["pid_rate_err_mean"] > 0.0
    assert features["pid_oscillation_pct"] > 0.0


def test_motor_extractor_records_thrust_loss_tanomaly():
    pipeline = FeaturePipeline()
    rcou = []
    gps = []
    for second in range(5):
        rcou.append(
            {
                "TimeUS": second * 1_000_000,
                "C1": 1910,
                "C2": 1915,
                "C3": 1920,
                "C4": 1912,
            }
        )
        gps.append({"TimeUS": second * 1_000_000, "Alt": 100 - second})

    parsed = {
        "metadata": {"vehicle_type": "Copter"},
        "messages": {"RCOU": rcou, "GPS": gps},
        "parameters": {},
        "errors": [],
        "events": [],
        "mode_changes": [],
        "status_messages": [],
    }
    features = pipeline.extract(parsed)
    assert features["_thrust_loss_tanomaly"] >= 0
    assert features["_thrust_loss_descent_detected"] == 1.0


def test_rover_pipeline_disables_hover_related_extractors():
    pipeline = FeaturePipeline()
    parsed = {
        "metadata": {"vehicle_type": "Rover"},
        "messages": {
            "VIBE": [{"TimeUS": 1_000_000, "VibeX": 50.0, "VibeY": 50.0, "VibeZ": 50.0}],
            "RCOU": [{"TimeUS": 1_000_000, "C1": 1900, "C2": 1900, "C3": 1900, "C4": 1900}],
            "CTUN": [{"TimeUS": 1_000_000, "ThO": 0.99, "Alt": 10, "DAlt": 20, "CRt": 0.0}],
        },
        "parameters": {},
        "errors": [],
        "events": [],
        "mode_changes": [],
        "status_messages": [],
    }
    features = pipeline.extract(parsed)
    assert features["vibe_z_max"] == 0.0
    assert features["motor_saturation_pct"] == 0.0
    assert features["ctrl_thr_saturated_pct"] == 0.0
