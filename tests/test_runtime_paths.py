from pathlib import Path

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
    assert Path(classifier.scaler_path) == MODELS_DIR / "scaler.joblib"
    assert Path(retrieval.known_failures_path) == KNOWN_FAILURES_PATH
