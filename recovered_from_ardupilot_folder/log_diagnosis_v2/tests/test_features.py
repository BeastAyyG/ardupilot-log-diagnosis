from src.features.vibration import VibrationExtractor
from src.features.pipeline import FeaturePipeline


# Dummy message class to mock Mavlink messages
class DummyMsg:
    def __init__(self, msg_type, **kwargs):
        self.msg_type = msg_type
        for k, v in kwargs.items():
            setattr(self, k, v)

    def get_type(self):
        return self.msg_type


def test_vibration_extractor_with_data():
    msgs = {
        "VIBE": [
            DummyMsg("VIBE", VibeX=10, VibeY=5, VibeZ=20, Clip0=0, Clip1=0, Clip2=0),
            DummyMsg("VIBE", VibeX=15, VibeY=10, VibeZ=35, Clip0=1, Clip1=0, Clip2=0),
            DummyMsg("VIBE", VibeX=12, VibeY=8, VibeZ=25, Clip0=0, Clip1=0, Clip2=0),
        ]
    }
    extractor = VibrationExtractor(msgs)
    features = extractor.extract()

    assert features["vibe_x_max"] == 15.0
    assert features["vibe_z_max"] == 35.0
    assert features["vibe_clip_total"] == 1.0


def test_vibration_extractor_missing_data():
    extractor = VibrationExtractor({})
    features = extractor.extract()

    assert features["vibe_x_max"] == 0.0
    assert features["vibe_z_max"] == 0.0
    assert features["vibe_clip_total"] == 0.0


def test_pipeline_runs_all_extractors():
    msgs = {"VIBE": [DummyMsg("VIBE", VibeX=1, VibeY=1, VibeZ=1, Clip0=0, Clip1=0, Clip2=0)]}
    pipeline = FeaturePipeline()
    features = pipeline.extract_all(msgs)

    assert "vibe_x_mean" in features
    assert "vibe_clip_total" in features


def test_extractors_support_dict_messages():
    msgs = {
        "VIBE": [{"VibeX": 3.0, "VibeY": 2.0, "VibeZ": 4.0, "Clip": 2}],
        "MAG": [{"MagX": 10.0, "MagY": 20.0, "MagZ": 30.0}],
        "BAT": [{"Volt": 12.1, "Curr": 8.0}],
        "GPS": [{"HDop": 1.2, "NSats": 11, "Status": 3}],
        "RCOU": [{"C1": 1100, "C2": 1200, "C3": 1300, "C4": 1400}],
        "ATT": [{"Roll": 2.0, "Pitch": 1.0, "DesRoll": 1.5}],
    }
    features = FeaturePipeline().extract_all(msgs)

    assert features["vibe_clip_total"] == 2.0
    assert features["mag_field_mean"] > 0.0
    assert features["bat_volt_min"] > 0.0
    assert features["gps_fix_pct"] == 100.0
    assert features["motor_spread_max"] == 300.0
    assert features["att_desroll_err"] == 0.5
