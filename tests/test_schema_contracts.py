from src.constants import FEATURE_NAMES, VALID_LABELS
from src.contracts import DiagnosisDict
from src.diagnosis.rule_engine import RuleEngine
from src.features.pipeline import FeaturePipeline


def test_feature_schema_matches_pipeline_names():
    pipeline = FeaturePipeline()
    assert pipeline.get_feature_names() == FEATURE_NAMES


def test_feature_schema_matches_zero_extraction_keys():
    pipeline = FeaturePipeline()
    features = pipeline.extract({
        "metadata": {},
        "messages": {},
        "parameters": {},
        "errors": [],
        "events": [],
        "mode_changes": [],
        "status_messages": [],
    })
    extracted_keys = [k for k in features.keys() if not k.startswith("_")]
    assert extracted_keys == FEATURE_NAMES


def test_diagnosis_contract_keys_are_present():
    engine = RuleEngine()
    features = {name: 0.0 for name in FEATURE_NAMES}
    features["vibe_z_max"] = 100.0
    diagnoses = engine.diagnose(features)

    assert diagnoses, "Expected at least one diagnosis"
    for diagnosis in diagnoses:
        typed: DiagnosisDict = diagnosis
        assert typed["failure_type"] in VALID_LABELS
        assert isinstance(typed["confidence"], float)
        assert typed["severity"] in {"critical", "warning", "info"}
        assert isinstance(typed["detection_method"], str)
        assert isinstance(typed["evidence"], list)
        assert isinstance(typed["recommendation"], str)
        assert isinstance(typed["reason_code"], str)


def test_feature_metadata_contract_keys_are_present():
    pipeline = FeaturePipeline()
    features = pipeline.extract({
        "metadata": {"filepath": "test.BIN", "duration_sec": 0.0},
        "messages": {},
        "parameters": {},
        "errors": [],
        "events": [],
        "mode_changes": [],
        "status_messages": [],
    })
    metadata = features["_metadata"]
    assert "log_file" in metadata
    assert "duration_sec" in metadata
    assert "messages_found" in metadata
    assert "total_features" in metadata
    assert "extraction_success" in metadata
