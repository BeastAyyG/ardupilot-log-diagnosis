"""
Tests for the SITL detection scripts.

These tests use in-memory synthetic log data to validate the analysis logic
without requiring real .BIN log files.  The approach mirrors how the existing
feature extractors are tested (fake message dicts injected directly).
"""
import pytest
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Helpers: build fake RCOU/VIBE/GPS message sequences
# ---------------------------------------------------------------------------

def _make_rcou_record(c1, c2, c3, c4, time_us=0):
    """Create a minimal RCOU message dict."""
    return {"time_us": time_us, "channels": {"C1": c1, "C2": c2, "C3": c3, "C4": c4}}


def _healthy_rcou(n=50, base=1500, spread=100, start_time_us=0):
    """Healthy hover: four motors balanced near 1500 PWM."""
    records = []
    for i in range(n):
        t = start_time_us + i * 200_000  # 5 Hz
        records.append({
            "time_us": t,
            "channels": {
                "C1": base + spread // 2,
                "C2": base - spread // 2,
                "C3": base + spread // 4,
                "C4": base - spread // 4,
            },
        })
    return records


def _thrust_loss_rcou(n=50, start_time_us=0):
    """Thrust loss: all motors pegged near 1950 PWM."""
    records = []
    for i in range(n):
        t = start_time_us + i * 200_000
        records.append({
            "time_us": t,
            "channels": {"C1": 1950, "C2": 1940, "C3": 1960, "C4": 1945},
        })
    return records


def _imbalanced_rcou(n=50, start_time_us=0):
    """Motor imbalance: large spread between channels."""
    records = []
    for i in range(n):
        t = start_time_us + i * 200_000
        records.append({
            "time_us": t,
            "channels": {"C1": 1750, "C2": 1200, "C3": 1700, "C4": 1150},
        })
    return records


def _healthy_vibe(n=20, level=10.0):
    return [
        {"time_us": i * 100_000, "vibe_x": level, "vibe_y": level,
         "vibe_z": level, "clip0": 0.0, "clip1": 0.0, "clip2": 0.0}
        for i in range(n)
    ]


def _high_vibe(n=20, level=80.0, clips=200):
    return [
        {"time_us": i * 100_000, "vibe_x": level, "vibe_y": level,
         "vibe_z": level, "clip0": clips / n, "clip1": 0.0, "clip2": 0.0}
        for i in range(n)
    ]


def _healthy_gps(n=20):
    return [
        {"time_us": i * 200_000, "status": 3.0, "hdop": 1.2, "nsats": 12.0}
        for i in range(n)
    ]


def _gps_loss(n=20):
    half = n // 2
    records = [
        {"time_us": i * 200_000, "status": 3.0, "hdop": 1.2, "nsats": 12.0}
        for i in range(half)
    ]
    records += [
        {"time_us": (half + i) * 200_000, "status": 0.0, "hdop": 99.9, "nsats": 0.0}
        for i in range(n - half)
    ]
    return records


def _poor_gps(n=20):
    return [
        {"time_us": i * 200_000, "status": 3.0, "hdop": 6.0, "nsats": 4.0}
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Import helpers: load each script module by path without installing
# ---------------------------------------------------------------------------

def _load_script(name, relpath):
    """Load a scripts/ file as a module."""
    import importlib.util
    import os
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base, relpath)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def detect_motor():
    return _load_script("detect_motor_loss", "scripts/detect_motor_loss.py")


@pytest.fixture(scope="module")
def detect_vibe():
    return _load_script("detect_high_vibration", "scripts/detect_high_vibration.py")


@pytest.fixture(scope="module")
def detect_gps():
    return _load_script("detect_gps_failure", "scripts/detect_gps_failure.py")


@pytest.fixture(scope="module")
def analyze_thrust():
    return _load_script("analyze_thrust", "scripts/analyze_thrust.py")


# ---------------------------------------------------------------------------
# detect_motor_loss tests
# ---------------------------------------------------------------------------

class TestDetectMotorLoss:
    def _run(self, mod, records):
        """Call the private analysis logic directly with fake RCOU records."""
        with patch.object(mod, "_parse_rcou", return_value=records):
            return mod.analyze("fake.BIN")

    def test_healthy_no_fault(self, detect_motor):
        result = self._run(detect_motor, _healthy_rcou())
        assert result["fault"] is False
        assert result["fault_type"] is None
        assert result["confidence"] == 0.0

    def test_thrust_loss_detected(self, detect_motor):
        # Thrust loss: motors pegged near 1950 from the start
        # Add startup period (10s) + fault period so post-startup samples are captured
        startup = _healthy_rcou(n=60, start_time_us=0)  # 12 seconds at 5Hz
        fault = _thrust_loss_rcou(n=100, start_time_us=startup[-1]["time_us"] + 200_000)
        records = startup + fault
        result = self._run(detect_motor, records)
        assert result["fault"] is True
        assert result["fault_type"] == "thrust_loss"
        assert result["confidence"] >= 0.40

    def test_motor_imbalance_detected(self, detect_motor):
        # Imbalanced motors: large spread sustained
        startup = _healthy_rcou(n=60, start_time_us=0)
        fault = _imbalanced_rcou(n=100, start_time_us=startup[-1]["time_us"] + 200_000)
        records = startup + fault
        result = self._run(detect_motor, records)
        assert result["fault"] is True
        assert result["fault_type"] in ("thrust_loss", "motor_imbalance")

    def test_insufficient_data(self, detect_motor):
        result = self._run(detect_motor, [])
        assert result["fault"] is False
        assert "Insufficient" in result["summary"]

    def test_evidence_has_required_keys(self, detect_motor):
        startup = _healthy_rcou(n=60, start_time_us=0)
        fault = _thrust_loss_rcou(n=100, start_time_us=startup[-1]["time_us"] + 200_000)
        result = self._run(detect_motor, startup + fault)
        for ev in result["evidence"]:
            assert "feature" in ev
            assert "value" in ev
            assert "threshold" in ev

    def test_first_fault_time_populated(self, detect_motor):
        startup = _healthy_rcou(n=60, start_time_us=0)
        fault = _thrust_loss_rcou(n=100, start_time_us=startup[-1]["time_us"] + 200_000)
        result = self._run(detect_motor, startup + fault)
        if result["fault"]:
            assert result["first_fault_time_sec"] is not None
            assert result["first_fault_time_sec"] >= 0.0

    def test_ioerror_on_bad_file(self, detect_motor):
        with pytest.raises(IOError):
            detect_motor.analyze("/nonexistent/path/to/log.BIN")


# ---------------------------------------------------------------------------
# detect_high_vibration tests
# ---------------------------------------------------------------------------

class TestDetectHighVibration:
    def _run(self, mod, records):
        with patch.object(mod, "_parse_vibe", return_value=records):
            return mod.analyze("fake.BIN")

    def test_healthy_no_fault(self, detect_vibe):
        result = self._run(detect_vibe, _healthy_vibe())
        assert result["fault"] is False

    def test_high_vibration_detected(self, detect_vibe):
        result = self._run(detect_vibe, _high_vibe(level=80.0, clips=200))
        assert result["fault"] is True
        assert result["fault_type"] == "vibration_high"
        assert result["confidence"] >= 0.5

    def test_warning_level_detected(self, detect_vibe):
        # Just above warning threshold (30 m/s²)
        records = _healthy_vibe(n=20, level=35.0)
        result = self._run(detect_vibe, records)
        assert result["fault"] is True
        assert result["confidence"] > 0.0

    def test_clip_only_is_fault(self, detect_vibe):
        # Low vibration values but clipping events
        records = [
            {"time_us": i * 100_000, "vibe_x": 5.0, "vibe_y": 5.0,
             "vibe_z": 5.0, "clip0": 10.0, "clip1": 0.0, "clip2": 0.0}
            for i in range(20)
        ]
        result = self._run(detect_vibe, records)
        assert result["fault"] is True

    def test_insufficient_data(self, detect_vibe):
        result = self._run(detect_vibe, [])
        assert result["fault"] is False

    def test_evidence_structure(self, detect_vibe):
        result = self._run(detect_vibe, _high_vibe())
        for ev in result["evidence"]:
            assert "feature" in ev
            assert "value" in ev
            assert "threshold" in ev

    def test_ioerror_on_bad_file(self, detect_vibe):
        with pytest.raises(IOError):
            detect_vibe.analyze("/nonexistent/path/to/log.BIN")


# ---------------------------------------------------------------------------
# detect_gps_failure tests
# ---------------------------------------------------------------------------

class TestDetectGpsFailure:
    def _run(self, mod, records):
        with patch.object(mod, "_parse_gps", return_value=records):
            return mod.analyze("fake.BIN")

    def test_healthy_no_fault(self, detect_gps):
        result = self._run(detect_gps, _healthy_gps())
        assert result["fault"] is False

    def test_gps_loss_detected(self, detect_gps):
        result = self._run(detect_gps, _gps_loss())
        assert result["fault"] is True
        assert result["fault_type"] in ("gps_loss", "gps_quality_poor")
        assert result["confidence"] >= 0.40

    def test_poor_quality_detected(self, detect_gps):
        result = self._run(detect_gps, _poor_gps())
        assert result["fault"] is True
        assert result["fault_type"] == "gps_quality_poor"

    def test_insufficient_data(self, detect_gps):
        result = self._run(detect_gps, [])
        assert result["fault"] is False

    def test_first_fault_time_on_loss(self, detect_gps):
        result = self._run(detect_gps, _gps_loss())
        if result["fault"]:
            assert result["first_fault_time_sec"] is not None

    def test_evidence_structure(self, detect_gps):
        result = self._run(detect_gps, _gps_loss())
        for ev in result["evidence"]:
            assert "feature" in ev
            assert "value" in ev
            assert "threshold" in ev

    def test_ioerror_on_bad_file(self, detect_gps):
        with pytest.raises(IOError):
            detect_gps.analyze("/nonexistent/path/to/log.BIN")


# ---------------------------------------------------------------------------
# analyze_thrust tests
# ---------------------------------------------------------------------------

class TestAnalyzeThrust:
    def _run(self, mod, rcou_records, ctun_records=None):
        ctun_records = ctun_records or []
        with patch.object(mod, "_parse_log", return_value=(rcou_records, ctun_records)):
            return mod.analyze("fake.BIN")

    def test_healthy_no_fault(self, analyze_thrust):
        result = self._run(analyze_thrust, _healthy_rcou())
        assert result["fault"] is False
        assert result["fault_type"] is None

    def test_thrust_loss_rcou_only(self, analyze_thrust):
        startup = _healthy_rcou(n=60, start_time_us=0)
        fault = _thrust_loss_rcou(n=100, start_time_us=startup[-1]["time_us"] + 200_000)
        result = self._run(analyze_thrust, startup + fault)
        assert result["fault"] is True
        assert result["fault_type"] == "thrust_loss"

    def test_thrust_loss_with_ctun(self, analyze_thrust):
        startup = _healthy_rcou(n=60, start_time_us=0)
        fault = _thrust_loss_rcou(n=100, start_time_us=startup[-1]["time_us"] + 200_000)
        ctun = [
            {"time_us": i * 200_000, "tho": 0.98, "alt_err": 8.0}
            for i in range(80)
        ]
        result = self._run(analyze_thrust, startup + fault, ctun)
        assert result["fault"] is True
        assert result["confidence"] >= 0.50

    def test_recommendations_present_on_fault(self, analyze_thrust):
        startup = _healthy_rcou(n=60, start_time_us=0)
        fault = _thrust_loss_rcou(n=100, start_time_us=startup[-1]["time_us"] + 200_000)
        result = self._run(analyze_thrust, startup + fault)
        if result["fault"]:
            assert len(result["recommendations"]) > 0

    def test_rcou_available_flag(self, analyze_thrust):
        startup = _healthy_rcou(n=60, start_time_us=0)
        result = self._run(analyze_thrust, startup)
        assert result["rcou_available"] is True

    def test_insufficient_rcou(self, analyze_thrust):
        result = self._run(analyze_thrust, [])
        assert result["fault"] is False
        assert "Insufficient" in result["summary"]

    def test_result_has_all_keys(self, analyze_thrust):
        result = self._run(analyze_thrust, _healthy_rcou())
        for key in ("fault", "fault_type", "confidence", "evidence",
                    "first_fault_time_sec", "rcou_available", "ctun_available",
                    "summary", "recommendations"):
            assert key in result

    def test_ioerror_on_bad_file(self, analyze_thrust):
        with pytest.raises(IOError):
            analyze_thrust.analyze("/nonexistent/path/to/log.BIN")
