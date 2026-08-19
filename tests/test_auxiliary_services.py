from __future__ import annotations

import importlib.util
import sys

import pytest
from pathlib import Path


def _load_module(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, Path(path))
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_llm_orchestrator_explanation_is_grounded_and_does_not_invent_findings():
    module = _load_module("llm-orchestrator/main.py", "grounded_llm_orchestrator")

    result = module._grounded_explanation(
        {
            "explain_data": {
                "decision": {
                    "status": "uncertain",
                    "requires_human_review": True,
                    "top_guess": None,
                }
            },
            "diagnoses": [],
        },
        "what happened?",
    )

    assert result["status"] == "grounded"
    assert result["model"] == "deterministic_grounded"
    assert result["write_parameters"] is False
    assert "vibration_high" not in result["explanation"]
    assert result["hypothesis"] is None


def test_llm_orchestrator_only_repeats_supplied_recommendation():
    module = _load_module("llm-orchestrator/main.py", "grounded_llm_orchestrator_with_finding")

    result = module._grounded_explanation(
        {
            "decision": {"status": "confirmed", "requires_human_review": False, "top_guess": "gps_quality_poor"},
            "diagnoses": [{"failure_type": "gps_quality_poor", "recommendation": "Review antenna placement."}],
        },
        None,
    )

    assert "gps_quality_poor" in result["explanation"]
    assert result["hypothesis"] == "Review antenna placement."


def test_llm_orchestrator_readiness_declares_grounded_only_mode():
    module = _load_module("llm-orchestrator/main.py", "grounded_llm_orchestrator_ready")

    response = module.readiness_check()

    assert response["status"] == "ready"
    assert response["mode"] == "grounded_only"
    assert response["model_ready"] is False
    assert response["write_parameters"] is False


def test_temporal_layer_refuses_unfitted_hmm_instead_of_returning_healthy():
    if importlib.util.find_spec("hmmlearn") is None:
        pytest.skip("temporal-layer optional dependency is not installed in the core environment")
    temporal_root = str(Path("temporal-layer").resolve())
    sys.path.insert(0, temporal_root)
    try:
        module = _load_module("temporal-layer/main.py", "safe_temporal_layer")
        from fastapi.testclient import TestClient

        client = TestClient(module.app)
        response = client.post("/filter", json={"features": [[1.0, 2.0]]})
        assert response.status_code == 503
        assert "not fitted" in response.json()["detail"]
        assert client.get("/ready").status_code == 503
    finally:
        sys.path.remove(temporal_root)


def test_temporal_layer_rejects_oversized_feature_sequences():
    if importlib.util.find_spec("hmmlearn") is None:
        pytest.skip("temporal-layer optional dependency is not installed in the core environment")
    temporal_root = str(Path("temporal-layer").resolve())
    sys.path.insert(0, temporal_root)
    try:
        module = _load_module("temporal-layer/main.py", "safe_temporal_layer_limits")
        from fastapi.testclient import TestClient

        client = TestClient(module.app)
        response = client.post("/filter", json={"features": [[1.0]] * (module.MAX_FEATURE_ROWS + 1)})
        assert response.status_code == 413
    finally:
        sys.path.remove(temporal_root)
