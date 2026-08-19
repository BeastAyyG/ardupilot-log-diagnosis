from __future__ import annotations

import json
import subprocess
import sys
import time

import pytest

from benchmarks.diagnostic import _cold_observation
from benchmarks.support import write_synthetic_arrow


def _run_probe(source: str) -> dict[str, object]:
    completed = subprocess.run(
        [sys.executable, "-c", source],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_cli_import_is_lazy_and_under_boot_target():
    result = _run_probe(
        "import json, sys, time; start = time.perf_counter(); "
        "import src.cli.main; elapsed = (time.perf_counter() - start) * 1000; "
        "print(json.dumps({'elapsed_ms': elapsed, 'commands_loaded': 'src.cli.commands' in sys.modules}))"
    )

    assert result["commands_loaded"] is False
    assert float(result["elapsed_ms"]) < 150.0


def test_optional_parser_and_spectrum_imports_are_deferred():
    result = _run_probe(
        "import json, sys; import src.core.ingestion.arrow_parser; "
        "arrow = 'pyarrow.compute' in sys.modules; "
        "import src.core.dynamics.welch_fft; "
        "print(json.dumps({'compute_loaded': arrow, 'signal_loaded': 'scipy.signal' in sys.modules}))"
    )

    assert result == {"compute_loaded": False, "signal_loaded": False}


def test_ml_loader_is_optional_and_deferred():
    result = _run_probe(
        "import json, sys; import src.diagnosis.ml_classifier; "
        "print(json.dumps({'joblib_loaded': 'joblib' in sys.modules}))"
    )

    assert result["joblib_loaded"] is False


def test_numpy_welch_fallback_finds_real_tone_without_scipy_import():
    result = _run_probe(
        "import json, sys; import numpy as np; "
        "from src.core.dynamics.welch_fft import extract_welch_psd; "
        "t = np.arange(4000) / 1000.0; signal = np.sin(2*np.pi*125*t); "
        "spectrum = extract_welch_psd(signal, 1000.0, nperseg=1000); "
        "print(json.dumps({'frequency': spectrum.ins_hntch_freq, 'scipy_loaded': 'scipy.signal' in sys.modules}))"
    )

    assert result["scipy_loaded"] is False
    assert float(result["frequency"]) == pytest.approx(125.0)


def test_fresh_diagnostic_process_is_measured_against_cold_target(tmp_path):
    workload = tmp_path / "cold.arrow"
    write_synthetic_arrow(workload, target_bytes=1_000_000)

    started = time.perf_counter()
    result = _cold_observation(workload)
    test_elapsed_ms = (time.perf_counter() - started) * 1000.0

    assert result["status"] == "measured"
    assert float(result["observed_ms"]) > 0.0
    assert float(result["process_elapsed_ms"]) <= test_elapsed_ms
    assert result["target_met"] is (float(result["process_elapsed_ms"]) < 250.0)
