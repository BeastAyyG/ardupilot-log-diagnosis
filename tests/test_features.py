from src.features.pipeline import FeaturePipeline
from src.constants import FEATURE_NAMES

from src.features.compass import CompassExtractor
from src.features.control import ControlExtractor
from src.features.system import SystemExtractor
from src.features.fft_analysis import FFTExtractor
from src.features.gps import GPSExtractor
from src.features.attitude import AttitudeExtractor
from src.features.motors import MotorExtractor
from src.features.power import PowerExtractor
from src.features.imu import IMUExtractor
from src.features.events import EventExtractor

def test_all_features_numerical():
    pipeline = FeaturePipeline()
    # Mocking parsed log
    parsed_mock = {"messages": {}, "metadata": {"filepath": "test.BIN"}}
    features = pipeline.extract(parsed_mock)
    
    for k, v in features.items():
        if not k.startswith("_"):
            assert isinstance(v, (int, float))
            
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
    assert features["ekf_flags_error_pct"] == 0.0

def test_pipeline_integration():
    pipeline = FeaturePipeline()
    features = pipeline.extract({"messages": {}})
    assert "_metadata" in features
    
def test_feature_count():
    pipeline = FeaturePipeline()
    assert len(pipeline.get_feature_names()) == len(FEATURE_NAMES)
    assert set(pipeline.get_feature_names()) == set(FEATURE_NAMES)


# ---------------------------------------------------------------------------
# Individual extractor tests (4b — coverage for previously untested extractors)
# ---------------------------------------------------------------------------

def _make(extractor_cls, messages):
    """Instantiate an extractor with *messages* and empty parameters."""
    return extractor_cls(messages, {})


def test_compass_extractor():
    msgs = [{"MagX": 100.0, "MagY": 200.0, "MagZ": 300.0, "TimeUS": 1000000}]
    ext = _make(CompassExtractor, {"MAG": msgs})
    result = ext.extract()
    assert result["mag_field_mean"] > 0
    assert set(CompassExtractor.FEATURE_NAMES).issubset(result.keys())


def test_compass_extractor_empty():
    ext = _make(CompassExtractor, {})
    result = ext.extract()
    assert all(v == 0.0 for k, v in result.items() if not k.startswith("_") and v != -1.0)


def test_control_extractor():
    msgs = [{"ThO": 0.5, "DAlt": 10.0, "Alt": 9.5, "CRt": 1.0, "ThH": 0.4}]
    ext = _make(ControlExtractor, {"CTUN": msgs})
    result = ext.extract()
    assert result["ctrl_thr_out_mean"] == 0.5
    assert result["ctrl_thr_hover_ratio"] > 0
    assert set(ControlExtractor.FEATURE_NAMES).issubset(result.keys())


def test_control_extractor_saturation():
    msgs = [{"ThO": 0.99, "DAlt": 10.0, "Alt": 10.0, "CRt": 0.0}] * 10
    ext = _make(ControlExtractor, {"CTUN": msgs})
    result = ext.extract()
    assert result["ctrl_thr_saturated_pct"] == 1.0


def test_system_extractor():
    pm_msgs = [{"NLon": 2.0, "MaxT": 500.0, "Load": 60.0, "IErr": 1.0}]
    powr_msgs = [{"Vcc": 5.0, "VServo": 5.2}]
    ext = _make(SystemExtractor, {"PM": pm_msgs, "POWR": powr_msgs})
    result = ext.extract()
    assert result["sys_long_loops"] == 2.0
    assert result["sys_max_loop_time"] == 500.0
    assert result["sys_vcc_min"] == 5.0
    assert set(SystemExtractor.FEATURE_NAMES).issubset(result.keys())


def test_fft_extractor_with_ftn1():
    msgs = [{"PkAvg": 120.0, "SnX": 10.0, "SnY": 20.0, "SnZ": 30.0}]
    ext = _make(FFTExtractor, {"FTN1": msgs})
    result = ext.extract()
    assert result["fft_dominant_freq_x"] == 120.0
    assert result["fft_peak_power_z"] == 30.0
    assert set(FFTExtractor.FEATURE_NAMES).issubset(result.keys())


def test_fft_extractor_no_data():
    ext = _make(FFTExtractor, {})
    result = ext.extract()
    assert all(v == 0.0 for v in result.values())


def test_gps_extractor():
    msgs = [
        {"HDop": 1.2, "NSats": 12, "Status": 3, "TimeUS": 1000000},
        {"HDop": 1.5, "NSats": 10, "Status": 3, "TimeUS": 2000000},
    ]
    ext = _make(GPSExtractor, {"GPS": msgs})
    result = ext.extract()
    assert result["gps_hdop_mean"] > 0
    assert result["gps_nsats_mean"] > 0
    assert result["gps_fix_pct"] == 1.0
    assert set(GPSExtractor.FEATURE_NAMES).issubset(result.keys())


def test_attitude_extractor():
    # Note: Roll/Pitch are abs()'d in the extractor, so use values with
    # different magnitudes to get non-zero std.
    msgs = [
        {"Roll": 2.0, "Pitch": 1.0, "DesRoll": 4.0, "TimeUS": 1000000},
        {"Roll": -10.0, "Pitch": -8.0, "DesRoll": -4.0, "TimeUS": 2000000},
    ]
    ext = _make(AttitudeExtractor, {"ATT": msgs})
    result = ext.extract()
    assert result["att_roll_max"] == 10.0  # abs(-10)
    assert result["att_pitch_max"] == 8.0  # abs(-8)
    assert result["att_desroll_err"] > 0
    assert set(AttitudeExtractor.FEATURE_NAMES).issubset(result.keys())


def test_motor_extractor():
    # First 10s are skipped for spread/tanomaly, so provide messages at t=0
    # (for output_mean) and t>10s (for spread).
    msgs = [
        {"C1": 1500, "C2": 1600, "C3": 1500, "C4": 1400, "TimeUS": 0},
        {"C1": 1500, "C2": 1700, "C3": 1500, "C4": 1400, "TimeUS": 11000000},
    ]
    ext = _make(MotorExtractor, {"RCOU": msgs})
    result = ext.extract()
    assert result["motor_spread_mean"] > 0   # post-10s sample has spread 300
    assert result["motor_output_mean"] > 0   # all samples contribute
    assert result["motor_max_output"] == 1700.0
    assert set(MotorExtractor.FEATURE_NAMES).issubset(result.keys())


def test_power_extractor():
    msgs = [
        {"Volt": 12.5, "Curr": 10.0, "TimeUS": 1000000},
        {"Volt": 11.8, "Curr": 15.0, "TimeUS": 2000000},
    ]
    ext = _make(PowerExtractor, {"BAT": msgs})
    result = ext.extract()
    assert result["bat_volt_min"] == 11.8
    assert result["bat_volt_max"] == 12.5
    assert result["bat_curr_mean"] == 12.5
    assert set(PowerExtractor.FEATURE_NAMES).issubset(result.keys())


def test_imu_extractor():
    msgs = [
        {"AccX": 0.1, "AccY": 0.2, "AccZ": -9.8, "GyrX": 0.01, "GyrY": 0.02, "GyrZ": 0.0},
        {"AccX": 0.15, "AccY": 0.25, "AccZ": -9.7, "GyrX": 0.015, "GyrY": 0.025, "GyrZ": 0.005},
    ]
    ext = _make(IMUExtractor, {"IMU": msgs})
    result = ext.extract()
    assert result["imu_acc_x_std"] > 0
    assert result["imu_acc_z_std"] > 0
    assert set(IMUExtractor.FEATURE_NAMES).issubset(result.keys())


def test_event_extractor():
    err_msgs = [{"Subsys": 5, "ECode": 1}, {"Subsys": 12, "ECode": 1}]
    ev_msgs = [{"Id": 19}]
    mode_msgs = [{"ModeNum": 6, "Reason": 2}]
    ext = _make(EventExtractor, {"ERR": err_msgs, "EV": ev_msgs, "MODE": mode_msgs})
    result = ext.extract()
    assert result["evt_error_count"] == 2.0
    assert result["evt_crash_detected"] == 1.0
    assert result["evt_gps_lost_count"] == 1.0
    assert result["evt_radio_failsafe_count"] == 1.0
    assert result["evt_rc_lost_count"] == 1.0
    assert set(EventExtractor.FEATURE_NAMES).issubset(result.keys())


def test_event_extractor_empty():
    ext = _make(EventExtractor, {})
    result = ext.extract()
    assert result["evt_error_count"] == 0.0
    assert result["evt_crash_detected"] == 0.0
