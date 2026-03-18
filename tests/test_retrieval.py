from pathlib import Path

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


def test_known_failures_populated():
    """known_failures.json must have at least one entry per major label."""
    from src.retrieval.similarity import FailureRetrieval
    r = FailureRetrieval()
    assert len(r.known.get("failures", [])) >= 8, (
        "known_failures.json must contain representative cases for all major failure types. "
        "Run the retrieval seeding script or update models/known_failures.json."
    )
    labels = {c["failure_type"] for c in r.known["failures"]}
    required = {"vibration_high", "compass_interference", "power_instability",
                "ekf_failure", "motor_imbalance", "rc_failsafe"}
    missing = required - labels
    assert not missing, f"known_failures.json missing cases for: {missing}"


def test_retrieval_returns_results_for_vibration():
    """find_similar() must return at least one match for a vibration feature set."""
    from src.retrieval.similarity import FailureRetrieval
    from src.constants import FEATURE_NAMES
    features = {k: 0.0 for k in FEATURE_NAMES}
    features.update({"vibe_z_max": 70.0, "vibe_clip_total": 200.0, "vibe_z_std": 12.0})
    r = FailureRetrieval()
    similar = r.find_similar(features)
    assert len(similar) >= 1, "Expected at least one similar case for high-vibration features"
    assert similar[0]["failure_type"] == "vibration_high"
    assert similar[0]["similarity"] >= 0.7


def test_default_known_failures_path_is_repo_relative(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    retrieval = FailureRetrieval()

    assert Path(retrieval.known_failures_path).is_absolute()
    assert Path(retrieval.known_failures_path).exists()
    assert retrieval.known.get("failures")
