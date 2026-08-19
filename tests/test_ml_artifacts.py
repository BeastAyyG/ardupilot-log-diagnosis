import json

from src.cli.formatter import DiagnosisFormatter
from src.constants import FEATURE_NAMES
from src.diagnosis import ml_classifier
from src.diagnosis.ml_classifier import MLClassifier


def test_current_model_can_use_rule_only_runtime_features():
    classifier = MLClassifier()
    assert classifier.available is True
    assert set(classifier.feature_columns).issubset(set(FEATURE_NAMES))
    prediction = classifier.predict({name: 0.0 for name in classifier.feature_columns})
    assert isinstance(prediction, list)
    assert classifier.get_inference_window_config()["verified"] is False
    assert "brownout" in classifier.unsupported_labels


def test_ml_classifier_falls_back_when_manifest_missing(tmp_path):
    (tmp_path / "classifier.joblib").write_text("x")
    (tmp_path / "scaler.joblib").write_text("x")
    (tmp_path / "feature_columns.json").write_text("[]")
    (tmp_path / "label_columns.json").write_text("[]")

    classifier = MLClassifier(model_dir=str(tmp_path))
    assert classifier.available is False
    assert "manifest" in classifier.unavailable_reason


def test_schema_columns_survive_classifier_deserialization_failure(tmp_path, monkeypatch):
    class FailingJoblib:
        def load(self, _path):
            raise RuntimeError("optional classifier runtime unavailable")

    for artifact in ("classifier.joblib", "scaler.joblib", "manifest.json"):
        (tmp_path / artifact).write_text("{}")
    (tmp_path / "feature_columns.json").write_text('["first", "second"]')
    (tmp_path / "label_columns.json").write_text('["healthy"]')
    monkeypatch.setattr(ml_classifier, "_load_joblib", lambda: FailingJoblib())

    classifier = MLClassifier(model_dir=tmp_path)

    assert classifier.feature_columns == ["first", "second"]
    assert classifier.label_columns == ["healthy"]
    assert classifier.available is False
    assert "failed to load ml artifacts" in classifier.unavailable_reason


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
