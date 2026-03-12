import json

from src.cli.formatter import DiagnosisFormatter
from src.diagnosis.ml_classifier import MLClassifier


def test_ml_classifier_falls_back_when_manifest_missing(tmp_path):
    (tmp_path / "classifier.joblib").write_text("x")
    (tmp_path / "scaler.joblib").write_text("x")
    (tmp_path / "feature_columns.json").write_text("[]")
    (tmp_path / "label_columns.json").write_text("[]")

    classifier = MLClassifier(model_dir=str(tmp_path))
    assert classifier.available is False
    assert "manifest" in classifier.unavailable_reason


def test_json_output_includes_runtime_info():
    formatter = DiagnosisFormatter()
    payload = formatter.format_json(
        [],
        {"log_file": "demo.BIN", "duration_sec": 0.0, "vehicle_type": "Copter", "firmware": "test"},
        {},
        decision={"status": "healthy", "requires_human_review": False, "top_guess": None, "top_confidence": 0.0, "rationale": [], "ranked_subsystems": []},
        runtime_info={"engine": "hybrid", "ml_available": False, "ml_reason": "manifest schema mismatch"},
    )
    data = json.loads(payload)
    assert data["runtime"]["ml_available"] is False
    assert data["runtime"]["engine"] == "hybrid"
