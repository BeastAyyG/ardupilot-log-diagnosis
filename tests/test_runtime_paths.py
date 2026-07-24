from pathlib import Path

import src.runtime_paths as runtime_paths
from src.diagnosis.anomaly_detector import AnomalyDetector
from src.diagnosis.ml_classifier import MLClassifier
from src.retrieval.similarity import FailureRetrieval
from src.runtime_paths import KNOWN_FAILURES_PATH, MODELS_DIR


def test_default_artifact_paths_are_repo_relative():
    anomaly_detector = AnomalyDetector()
    classifier = MLClassifier()
    retrieval = FailureRetrieval()

    assert Path(anomaly_detector.model_path) == MODELS_DIR / "anomaly_detector.joblib"
    assert Path(classifier.model_path) == MODELS_DIR / "classifier.joblib"
    assert Path(classifier.imputer_path) == MODELS_DIR / "imputer.joblib"
    assert Path(classifier.scaler_path) == MODELS_DIR / "scaler.joblib"
    assert Path(retrieval.known_failures_path) == KNOWN_FAILURES_PATH


def test_default_models_dir_finds_wheel_data_files(tmp_path, monkeypatch):
    installed_models = (
        tmp_path / "share" / "ardupilot-log-diagnosis" / "models"
    )
    installed_models.mkdir(parents=True)

    monkeypatch.delenv("ARDUPILOT_DIAGNOSIS_MODEL_DIR", raising=False)
    monkeypatch.setattr(runtime_paths, "project_root", lambda: tmp_path / "site-packages")
    monkeypatch.setattr(runtime_paths.sys, "prefix", str(tmp_path))

    assert runtime_paths.default_models_dir() == installed_models.resolve()
