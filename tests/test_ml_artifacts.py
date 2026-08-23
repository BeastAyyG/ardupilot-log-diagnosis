import hashlib
import json

import joblib
import numpy as np
import pytest

from src.cli.formatter import DiagnosisFormatter
from src.constants import FEATURE_NAMES, VALID_LABELS
from src.diagnosis import ml_classifier
from src.diagnosis.artifact_authorization import (
    TRUST_ENV_VAR,
    authorization_decision_sha256,
)
from src.diagnosis.ml_classifier import MLClassifier
from training.runtime_model import IdentityScaler


class _TestPredictor:
    def predict_proba(self, values):
        return np.tile(np.array([[0.8, 0.2]]), (len(values), 1))


def _hash_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash_list(values):
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def _write_v3_candidate(root, *, authorize=False, version=3, bundle_classes=None):
    root.mkdir(parents=True, exist_ok=True)
    classes = ["healthy", "thrust_loss"]
    (root / "feature_columns.json").write_text(json.dumps(FEATURE_NAMES))
    (root / "label_columns.json").write_text(json.dumps(classes))
    (root / "rule_thresholds.yaml").write_text("healthy:\n  probability: 0.5\n")
    joblib.dump(
        {"model": _TestPredictor(), "classes": bundle_classes or classes},
        root / "classifier.joblib",
    )
    joblib.dump(IdentityScaler(len(FEATURE_NAMES)), root / "scaler.joblib")
    artifact_files = {
        name: _hash_file(root / name)
        for name in (
            "classifier.joblib",
            "scaler.joblib",
            "feature_columns.json",
            "label_columns.json",
            "rule_thresholds.yaml",
        )
    }
    manifest = {
        "artifact_schema_version": version,
        "release_status": "development_candidate_requires_blinded_confirmation",
        "feature_schema_hash": _hash_list(FEATURE_NAMES),
        "trained_label_schema_hash": _hash_list(classes),
        "runtime_label_schema_hash": _hash_list(VALID_LABELS),
        "threshold_config_hash": _hash_file(root / "rule_thresholds.yaml"),
        "artifact_files": artifact_files,
        "evaluation": {"non_promoting": True},
        "inference_window": {
            "version": 1,
            "window_sec": 30.0,
            "overlap": 0.5,
            "include_full_log": True,
            "aggregation": "max_raw_probability",
        },
    }
    (root / "manifest.json").write_text(json.dumps(manifest))
    if authorize:
        gate = {
            "schema": "logdiagnosis.synthetic-gate-evaluation/v2",
            "pass": True,
            "release_authorized": False,
            "evidence_sha256": "a" * 64,
            "policy_sha256": "b" * 64,
        }
        (root / "acceptance_gate_report.json").write_text(json.dumps(gate))
        receipt = {
            "schema": "logdiagnosis.model-promotion-authorization/v1",
            "status": "authorized",
            "receipt_id": "promotion-test-001",
            "candidate_manifest_sha256": _hash_file(root / "manifest.json"),
            "acceptance_gate_report_sha256": _hash_file(
                root / "acceptance_gate_report.json"
            ),
            "authorization_decision_sha256": None,
            "authorized_by": "independent-test-authority",
            "authorized_at": "2026-08-23T00:00:00Z",
        }
        receipt["authorization_decision_sha256"] = authorization_decision_sha256(
            receipt
        )
        receipt_bytes = json.dumps(receipt).encode()
        (root / "promotion_receipt.json").write_bytes(receipt_bytes)
        return hashlib.sha256(receipt_bytes).hexdigest()
    return None


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


def test_schema_v3_candidate_is_inert_until_manifest_bound_promotion(
    tmp_path, monkeypatch
):
    _write_v3_candidate(tmp_path)
    candidate = MLClassifier(model_dir=tmp_path)
    assert candidate.available is False
    assert "promotion authorization" in candidate.unavailable_reason

    receipt_sha = _write_v3_candidate(tmp_path, authorize=True)
    promoted = MLClassifier(model_dir=tmp_path)
    assert promoted.available is False
    assert "trust anchor" in promoted.unavailable_reason

    monkeypatch.setenv(TRUST_ENV_VAR, receipt_sha)
    trusted = MLClassifier(model_dir=tmp_path)
    assert trusted.available is True


def test_promotion_fails_closed_without_a_matching_trust_pin(tmp_path, monkeypatch):
    receipt_sha = _write_v3_candidate(tmp_path, authorize=True)
    monkeypatch.setenv(TRUST_ENV_VAR, "e" * 64)
    foreign = MLClassifier(model_dir=tmp_path)
    assert foreign.available is False
    assert "not pinned" in foreign.unavailable_reason

    monkeypatch.setenv(TRUST_ENV_VAR, receipt_sha)
    assert MLClassifier(model_dir=tmp_path).available is True


def test_tampered_decision_binding_fails_closed_even_when_pinned(tmp_path, monkeypatch):
    _write_v3_candidate(tmp_path, authorize=True)
    receipt_path = tmp_path / "promotion_receipt.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["authorized_at"] = "2026-08-24T00:00:00Z"
    tampered_bytes = json.dumps(receipt).encode()
    receipt_path.write_bytes(tampered_bytes)
    tampered_sha = hashlib.sha256(tampered_bytes).hexdigest()

    monkeypatch.setenv(TRUST_ENV_VAR, tampered_sha)
    classifier = MLClassifier(model_dir=tmp_path)
    assert classifier.available is False
    assert "decision binding" in classifier.unavailable_reason


def test_future_schema_and_bundle_class_mismatch_fail_closed(tmp_path, monkeypatch):
    future = tmp_path / "future"
    _write_v3_candidate(future, authorize=True, version=4)
    assert MLClassifier(model_dir=future).available is False

    mismatch = tmp_path / "mismatch"
    receipt_sha = _write_v3_candidate(
        mismatch,
        authorize=True,
        bundle_classes=["thrust_loss", "healthy"],
    )
    monkeypatch.setenv(TRUST_ENV_VAR, receipt_sha)
    classifier = MLClassifier(model_dir=mismatch)
    assert classifier.available is False
    assert "manifest schema mismatch" in classifier.unavailable_reason


@pytest.mark.parametrize("document", ["manifest", "gate", "receipt"])
def test_future_authorization_schemas_never_reach_deserialization(
    tmp_path, monkeypatch, document
):
    _write_v3_candidate(tmp_path, authorize=True)
    manifest_path = tmp_path / "manifest.json"
    gate_path = tmp_path / "acceptance_gate_report.json"
    receipt_path = tmp_path / "promotion_receipt.json"
    if document == "manifest":
        manifest = json.loads(manifest_path.read_text())
        manifest["artifact_schema_version"] = 4
        manifest_path.write_text(json.dumps(manifest))
    elif document == "gate":
        gate = json.loads(gate_path.read_text())
        gate["schema"] = "logdiagnosis.synthetic-gate-evaluation/v99"
        gate_path.write_text(json.dumps(gate))
        receipt = json.loads(receipt_path.read_text())
        receipt["acceptance_gate_report_sha256"] = _hash_file(gate_path)
        receipt["authorization_decision_sha256"] = authorization_decision_sha256(
            receipt
        )
        receipt_path.write_text(json.dumps(receipt))
    else:
        receipt = json.loads(receipt_path.read_text())
        receipt["schema"] = "logdiagnosis.model-promotion-authorization/v99"
        receipt_path.write_text(json.dumps(receipt))
    monkeypatch.setenv(TRUST_ENV_VAR, _hash_file(receipt_path))
    attempts = []
    monkeypatch.setattr(
        joblib, "load", lambda path: attempts.append(str(path))
    )

    classifier = MLClassifier(model_dir=tmp_path)

    assert classifier.available is False
    assert attempts == []


def test_deserialization_is_attempted_only_after_all_gates_pass(tmp_path, monkeypatch):
    _write_v3_candidate(tmp_path, authorize=True)
    receipt_sha = hashlib.sha256(
        (tmp_path / "promotion_receipt.json").read_bytes()
    ).hexdigest()
    monkeypatch.setenv(TRUST_ENV_VAR, receipt_sha)

    calls = []
    real_load = joblib.load

    def exploding_load(path):
        calls.append(str(path))
        raise RuntimeError("simulated unsafe deserialization")

    monkeypatch.setattr(joblib, "load", exploding_load)
    classifier = MLClassifier(model_dir=tmp_path)
    assert classifier.available is False
    assert "failed to load ml artifacts" in classifier.unavailable_reason
    assert len(calls) == 1

    monkeypatch.setattr(joblib, "load", real_load)

    tampered = tmp_path / "tampered"
    _write_v3_candidate(tampered, authorize=True)
    (tampered / "classifier.joblib").write_bytes(b"corrupted-payload")
    attempts = []
    monkeypatch.setattr(
        joblib, "load", lambda path: attempts.append(str(path)) or real_load(path)
    )
    broken = MLClassifier(model_dir=tampered)
    assert broken.available is False
    assert broken.unavailable_reason == "artifact integrity hash mismatch"
    assert attempts == []


def test_json_output_includes_runtime_info():
    formatter = DiagnosisFormatter()
    payload = formatter.format_json(
        [],
        {
            "log_file": "demo.BIN",
            "duration_sec": 0.0,
            "vehicle_type": "Copter",
            "firmware": "test",
        },
        {},
        decision={
            "status": "healthy",
            "requires_human_review": False,
            "top_guess": None,
            "top_confidence": 0.0,
            "rationale": [],
            "ranked_subsystems": [],
        },
        runtime_info={
            "engine": "hybrid",
            "ml_available": False,
            "ml_reason": "manifest schema mismatch",
        },
    )
    data = json.loads(payload)
    assert data["runtime"]["ml_available"] is False
    assert data["runtime"]["engine"] == "hybrid"
