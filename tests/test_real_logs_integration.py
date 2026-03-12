"""
Integration tests using real ArduPilot .BIN log files.

These tests load actual flight logs through the FULL pipeline:
    Parser → Feature Extraction → Rule Engine → Hybrid Engine → Decision Policy

They prove the tool works end-to-end on real data, not just mock dictionaries.
Tests are skipped gracefully if the data directory is not present (CI-safe).
"""

import pytest
from pathlib import Path

from src.parser.bin_parser import LogParser
from src.features.pipeline import FeaturePipeline
from src.diagnosis.hybrid_engine import HybridEngine
from src.diagnosis.decision_policy import evaluate_decision

# ── Data directory ──────────────────────────────────────────────────────────
DATA_DIR = Path("data/kaggle_backups/ardupilot-master-log-pool-v2")
SKIP_REASON = "Real log data not present (CI environment)"


def _has_data():
    if not DATA_DIR.exists():
        return False
    # Check if there are .bin files that are actually binary logs, not just LFS pointers
    for log_file in DATA_DIR.glob("*.bin"):
        # LFS pointer files are small (usually < 200 bytes). Real BIN logs are > 10KB.
        if log_file.stat().st_size > 1024:
            # Optionally check if it looks like an LFS pointer by reading the first bytes
            with open(log_file, "rb") as f:
                header = f.read(20)
                if not header.startswith(b"version https://git-lfs"):
                    return True
    return False


def _run_full_pipeline(log_path: str | Path) -> dict:
    """Run the complete diagnostic pipeline on a single .BIN file.

    Returns a dict with keys: features, diagnoses, decision.
    """
    parser = LogParser(str(log_path))
    parsed = parser.parse()

    pipeline = FeaturePipeline()
    features = pipeline.extract(parsed)

    engine = HybridEngine()
    diagnoses = engine.diagnose(features)

    decision = evaluate_decision(diagnoses)

    return {
        "parsed": parsed,
        "features": features,
        "diagnoses": diagnoses,
        "decision": decision,
    }


def _find_log(pattern: str) -> str:
    """Find the first log matching *pattern* in DATA_DIR."""
    matches = list(DATA_DIR.glob(f"*{pattern}*"))
    if not matches:
        pytest.skip(f"No log matching '{pattern}' in {DATA_DIR}")
    return str(matches[0])


# ═══════════════════════════════════════════════════════════════════════════
# CORE: Pipeline never crashes on ANY real log
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(not _has_data(), reason=SKIP_REASON)
class TestPipelineNoCrash:
    """Every single .BIN file must survive the full pipeline without exception."""

    def test_all_logs_survive_pipeline(self):
        """Run every log through the pipeline — zero crashes allowed."""
        logs = list(DATA_DIR.glob("*.bin"))
        assert len(logs) > 0, "No .bin files found"

        errors = []
        for log_path in logs:
            try:
                result = _run_full_pipeline(log_path)
                assert isinstance(result["diagnoses"], list)
                assert isinstance(result["decision"], dict)
            except Exception as e:
                errors.append(f"{log_path.name}: {type(e).__name__}: {e}")

        assert not errors, (
            f"Pipeline crashed on {len(errors)}/{len(logs)} logs:\n"
            + "\n".join(errors)
        )


# ═══════════════════════════════════════════════════════════════════════════
# GOLDEN LOG TESTS: Known failure type → correct diagnosis
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(not _has_data(), reason=SKIP_REASON)
class TestGoldenVibration:
    """Vibration logs must be detected as vibration_high."""

    def test_vibration_log_detected(self):
        log = _find_log("log_0001_vibration_high")
        result = _run_full_pipeline(log)
        diag_types = [d["failure_type"] for d in result["diagnoses"]]
        assert "vibration_high" in diag_types, (
            f"Expected vibration_high in {diag_types} for {Path(log).name}"
        )


@pytest.mark.skipif(not _has_data(), reason=SKIP_REASON)
class TestGoldenCompass:
    """Compass interference logs must be detected."""

    def test_compass_log_detected(self):
        log = _find_log("log_0009_compass_interference")
        result = _run_full_pipeline(log)
        diag_types = [d["failure_type"] for d in result["diagnoses"]]
        assert "compass_interference" in diag_types, (
            f"Expected compass_interference in {diag_types} for {Path(log).name}"
        )


@pytest.mark.skipif(not _has_data(), reason=SKIP_REASON)
class TestGoldenEKF:
    """EKF failure logs must be detected."""

    def test_ekf_log_detected(self):
        log = _find_log("log_0010_ekf_failure")
        result = _run_full_pipeline(log)
        diag_types = [d["failure_type"] for d in result["diagnoses"]]
        assert "ekf_failure" in diag_types, (
            f"Expected ekf_failure in {diag_types} for {Path(log).name}"
        )


@pytest.mark.skipif(not _has_data(), reason=SKIP_REASON)
class TestGoldenRCFailsafe:
    """RC failsafe logs must be detected."""

    def test_rc_failsafe_log_detected(self):
        log = _find_log("log_0008_rc_failsafe")
        result = _run_full_pipeline(log)
        diag_types = [d["failure_type"] for d in result["diagnoses"]]
        assert "rc_failsafe" in diag_types, (
            f"Expected rc_failsafe in {diag_types} for {Path(log).name}"
        )


@pytest.mark.skipif(not _has_data(), reason=SKIP_REASON)
class TestGoldenPower:
    """Power instability logs must be detected."""

    def test_power_log_detected(self):
        log = _find_log("log_0013_power_instability")
        result = _run_full_pipeline(log)
        diag_types = [d["failure_type"] for d in result["diagnoses"]]
        # Under root-cause precedence, older forum labels can be re-attributed to
        # the telemetry-visible propulsion fault that actually appears in the log.
        accepted = {"power_instability", "brownout", "motor_imbalance", "ekf_failure"}
        assert accepted.intersection(diag_types), (
            f"Expected one of {sorted(accepted)} in {diag_types} for {Path(log).name}"
        )


@pytest.mark.skipif(not _has_data(), reason=SKIP_REASON)
class TestGoldenThrustLoss:
    """Thrust loss logs must be detected."""

    def test_thrust_loss_log_detected(self):
        log = _find_log("log_0046_thrust_loss")
        result = _run_full_pipeline(log)
        diag_types = [d["failure_type"] for d in result["diagnoses"]]
        accepted = {"thrust_loss", "mechanical_failure", "power_instability", "motor_imbalance"}
        assert accepted.intersection(diag_types), (
            f"Expected one of {sorted(accepted)} in {diag_types} for {Path(log).name}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# CONTRACT: Every diagnosis has required output schema
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(not _has_data(), reason=SKIP_REASON)
class TestOutputSchema:
    """Every diagnosis on real logs must have complete evidence and recommendations."""

    def test_all_diagnoses_have_evidence(self):
        """Every diagnosis must include at least one evidence item."""
        logs = list(DATA_DIR.glob("*.bin"))[:10]  # sample 10 for speed
        for log_path in logs:
            result = _run_full_pipeline(log_path)
            for d in result["diagnoses"]:
                assert "failure_type" in d, f"Missing failure_type in {log_path.name}"
                assert "confidence" in d, f"Missing confidence in {log_path.name}"
                assert "evidence" in d, f"Missing evidence in {log_path.name}"
                assert "recommendation" in d, f"Missing recommendation in {log_path.name}"
                assert len(d["evidence"]) > 0, (
                    f"Empty evidence for {d['failure_type']} in {log_path.name}"
                )

    def test_decision_has_required_keys(self):
        """Decision policy output must have all required keys."""
        log = _find_log("log_0001_vibration_high")
        result = _run_full_pipeline(log)
        decision = result["decision"]
        required_keys = ["status", "requires_human_review", "top_guess", "top_confidence"]
        for key in required_keys:
            assert key in decision, f"Missing '{key}' in decision output"
