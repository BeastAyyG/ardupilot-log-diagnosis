from src.features.attitude import AttitudeExtractor
from src.features.compass import CompassExtractor
from src.features.control import ControlExtractor
from src.features.ekf import EKFExtractor
from src.features.events import EventExtractor
from src.features.fft_analysis import FFTExtractor
from src.features.gps import GPSExtractor
from src.features.imu import IMUExtractor
from src.features.motors import MotorExtractor
from src.features.power import PowerExtractor
from src.features.system import SystemExtractor
from src.features.vibration import VibrationExtractor
from src.parser.bin_parser import LogParser


EXTRACTORS = [
    VibrationExtractor,
    CompassExtractor,
    PowerExtractor,
    GPSExtractor,
    MotorExtractor,
    AttitudeExtractor,
    EKFExtractor,
    IMUExtractor,
    ControlExtractor,
    SystemExtractor,
    EventExtractor,
    FFTExtractor,
]


def test_parser_retains_all_extractor_dependency_messages():
    parser_messages = LogParser.INTERESTING_MESSAGE_TYPES
    missing = {}

    for extractor in EXTRACTORS:
        deps = extractor.dependency_messages()
        missing_deps = sorted(set(deps) - set(parser_messages))
        if missing_deps:
            missing[extractor.__name__] = missing_deps

    assert missing == {}, f"Parser missing extractor dependencies: {missing}"


def test_custom_dependency_extractors_declare_fallback_messages():
    assert PowerExtractor.dependency_messages() == ["BAT", "CURR"]
    assert EKFExtractor.dependency_messages() == ["XKF4", "NKF4"]
    assert SystemExtractor.dependency_messages() == ["PM", "POWR"]
    assert EventExtractor.dependency_messages() == ["ERR", "EV", "MODE"]
    assert FFTExtractor.dependency_messages() == ["FTN1", "IMU"]
