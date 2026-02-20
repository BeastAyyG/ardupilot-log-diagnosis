import pytest
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
