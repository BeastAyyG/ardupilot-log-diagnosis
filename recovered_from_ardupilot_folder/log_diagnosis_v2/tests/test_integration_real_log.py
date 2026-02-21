from pathlib import Path
from typing import Optional

import pytest

from src.features.pipeline import FeaturePipeline
from src.integration.cli import run_diagnosis
from src.parser.bin_parser import LogParser


def _find_real_log() -> Optional[Path]:
    repo_root = Path(__file__).resolve().parents[2]
    candidates = [
        repo_root / "logs" / "latest.BIN",
        repo_root / "ardupilot-log-diagnosis" / "test_logs" / "healthy" / "sitl_flight.BIN",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def test_real_log_feature_extraction_is_non_zero():
    log_path = _find_real_log()
    if log_path is None:
        pytest.skip("No real BIN fixture found in repository.")

    parsed = LogParser(str(log_path)).parse()
    features = FeaturePipeline().extract_all(parsed["messages"])
    non_zero = [v for v in features.values() if abs(float(v)) > 1e-9]

    assert parsed["metadata"]["total_messages"] > 0
    assert len(features) >= 30
    assert len(non_zero) > 0


def test_run_diagnosis_returns_report_for_real_log():
    log_path = _find_real_log()
    if log_path is None:
        pytest.skip("No real BIN fixture found in repository.")

    report = run_diagnosis(str(log_path), model_path="models/does-not-exist.pkl")

    assert "summary" in report
    assert "diagnoses" in report
    assert "features" in report
    assert report["metadata"]["total_messages"] > 0
