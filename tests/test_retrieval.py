import pytest
import os
from src.retrieval.similarity import FailureRetrieval

def test_empty_database(tmp_path):
    retrieval = FailureRetrieval(str(tmp_path / "empty.json"))
    res = retrieval.find_similar({"vibe_z_max": 100.0})
    assert len(res) == 0

def test_self_match(tmp_path):
    retrieval = FailureRetrieval(str(tmp_path / "test.json"))
    features = {"vibe_z_max": 100.0, "vibe_x_max": 50.0}
    retrieval.add_known_failure(features, "vibration_high", fix="Change props")
    
    res = retrieval.find_similar(features)
    assert len(res) > 0
    assert res[0]["similarity"] > 0.99
    assert res[0]["failure_type"] == "vibration_high"

def test_different_types(tmp_path):
    retrieval = FailureRetrieval(str(tmp_path / "test.json"))
    features1 = {"vibe_z_max": 100.0}
    retrieval.add_known_failure(features1, "vibration_high")
    
    features2 = {"mag_field_range": 300.0}
    res = retrieval.find_similar(features2)
    # The vectors are orthogonal, so sim should be 0.0, not returned
    assert len(res) == 0

def test_top_k(tmp_path):
    retrieval = FailureRetrieval(str(tmp_path / "test.json"))
    for i in range(5):
        retrieval.add_known_failure({"vibe_z_max": 100.0 + i}, "vibration_high")
        
    res = retrieval.find_similar({"vibe_z_max": 100.0}, top_k=3)
    assert len(res) == 3
