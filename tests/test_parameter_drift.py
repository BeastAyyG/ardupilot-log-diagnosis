"""Tests for in-flight parameter drift detection (issue #39)."""

from src.constants import ADVISORY_LABELS, FEATURE_NAMES, VALID_LABELS
from src.diagnosis.hybrid_engine import HybridEngine
from src.diagnosis.parameter_drift import (
    detect_drift_from_features,
    detect_parameter_drift,
    drift_findings,
    summarize_drift,
)
from src.diagnosis.rule_engine import RuleEngine
from src.diagnosis.rules.parameters import check_parameter_drift
from src.features.pipeline import FeaturePipeline

T0 = 1_000_000


def _parm(t_offset_us, name, value):
    return {"TimeUS": T0 + t_offset_us, "Name": name, "Value": value}


def _base_features():
    return {name: 0.0 for name in FEATURE_NAMES}


# --------------------------------------------------------------------------- #
# Core detector
# --------------------------------------------------------------------------- #
def test_detects_midflight_tuning_change():
    events = detect_parameter_drift(
        [_parm(0, "ATC_RAT_RLL_P", 0.135), _parm(40_000_000, "ATC_RAT_RLL_P", 0.200)]
    )
    assert len(events) == 1
    ev = events[0]
    assert ev["parameter"] == "ATC_RAT_RLL_P"
    assert ev["old_value"] == 0.135
    assert ev["new_value"] == 0.200
    assert ev["tuning_critical"] is True
    assert ev["t_sec"] == 40.0


def test_boot_dump_changes_are_ignored():
    events = detect_parameter_drift(
        [_parm(0, "ATC_RAT_RLL_P", 0.135), _parm(1_000_000, "ATC_RAT_RLL_P", 0.140)],
        settle_sec=5.0,
    )
    assert events == []


def test_auto_learned_and_stat_params_are_ignored():
    parm = [
        _parm(0, "MOT_THST_HOVER", 0.14),
        _parm(40_000_000, "MOT_THST_HOVER", 0.26),
        _parm(0, "STAT_FLTTIME", 500.0),
        _parm(41_000_000, "STAT_FLTTIME", 540.0),
        _parm(0, "MIS_TOTAL", 4.0),
        _parm(42_000_000, "MIS_TOTAL", 5.0),
    ]
    assert detect_parameter_drift(parm) == []


def test_repeated_identical_value_is_not_a_change():
    parm = [_parm(0, "ANGLE_MAX", 4500.0), _parm(40_000_000, "ANGLE_MAX", 4500.0)]
    assert detect_parameter_drift(parm) == []


def test_extra_ignore_names_respected():
    parm = [_parm(0, "MY_CUSTOM", 1.0), _parm(40_000_000, "MY_CUSTOM", 2.0)]
    assert detect_parameter_drift(parm, ignore_names={"MY_CUSTOM"}) == []
    assert len(detect_parameter_drift(parm)) == 1


def test_summary_aggregates_distinct_params_and_onset():
    parm = [
        _parm(0, "ATC_RAT_RLL_P", 0.135),
        _parm(30_000_000, "ATC_RAT_RLL_P", 0.20),
        _parm(0, "ATC_RAT_PIT_P", 0.135),
        _parm(45_000_000, "ATC_RAT_PIT_P", 0.18),
    ]
    summary = summarize_drift(detect_parameter_drift(parm))
    assert summary["count"] == 2.0
    assert summary["tanomaly"] == float(T0 + 30_000_000)
    assert summary["max_rel_change"] > 0.0


def test_empty_input():
    assert detect_parameter_drift(None) == []
    assert detect_parameter_drift([]) == []
    assert summarize_drift([]) == {"count": 0.0, "max_rel_change": 0.0, "tanomaly": -1.0}


def test_incremental_drift_below_threshold_still_detected():
    # Each individual step is < 10% relative, but the cumulative change vs the
    # post-boot baseline exceeds it. With the baseline-reset bug this would never
    # be flagged; with the fix the original baseline is retained until accepted.
    parm = [
        _parm(0, "ATC_RAT_RLL_P", 1.00),           # boot baseline
        _parm(10_000_000, "ATC_RAT_RLL_P", 1.05),  # +5% vs 1.00 -> below floor, ignored
        _parm(20_000_000, "ATC_RAT_RLL_P", 1.10),  # +10% vs 1.00 -> accepted
    ]
    events = detect_parameter_drift(parm, settle_sec=5.0, min_rel_change=0.10)
    assert len(events) == 1
    assert events[0]["old_value"] == 1.00          # baseline was NOT reset to 1.05
    assert abs(events[0]["new_value"] - 1.10) < 1e-9


# --------------------------------------------------------------------------- #
# Threshold overrides are honoured (detection deferred to active thresholds)
# --------------------------------------------------------------------------- #
def _features_with_raw(parm):
    features = _base_features()
    features["_raw_parm_messages"] = parm
    features["_metadata"] = {"vehicle_type": "Copter"}
    return features


def test_settle_threshold_override_applies_in_rule():
    # Change at T+3s: ignored under the default 5s settle window, but flagged
    # when the rule is given a custom 2s settle window.
    features = _features_with_raw(
        [_parm(0, "ATC_RAT_RLL_P", 0.135), _parm(3_000_000, "ATC_RAT_RLL_P", 0.20)]
    )
    assert check_parameter_drift(features, {}) is None
    result = check_parameter_drift(features, {"param_drift_settle_sec": 2.0})
    assert result is not None
    assert result["failure_type"] == "parameter_drift"


def test_min_rel_change_override_applies_in_findings():
    features = _features_with_raw(
        [_parm(0, "ATC_RAT_RLL_P", 1.00), _parm(40_000_000, "ATC_RAT_RLL_P", 1.05)]
    )
    # 5% change is flagged by default (min_rel_change=0)...
    assert len(drift_findings(features)) == 1
    # ...but suppressed when a 10% floor is configured.
    assert drift_findings(features, {"param_drift_min_rel_change": 0.10}) == []


def test_rule_engine_custom_thresholds_propagate_to_drift():
    parm = [_parm(0, "ATC_RAT_RLL_P", 0.135), _parm(3_000_000, "ATC_RAT_RLL_P", 0.20)]
    features = _features_with_raw(parm)

    default_engine = RuleEngine()
    default_engine.diagnose(features)
    assert default_engine.advisories == []  # within default 5s settle window

    base = dict(RuleEngine().thresholds)
    base["param_drift_settle_sec"] = 2.0
    custom_engine = RuleEngine(thresholds=base)
    custom_engine.diagnose(features)
    assert "parameter_drift" in [d["failure_type"] for d in custom_engine.advisories]


# --------------------------------------------------------------------------- #
# Rule
# --------------------------------------------------------------------------- #
def test_rule_returns_none_without_events():
    features = _features_with_raw([])
    assert check_parameter_drift(features, {}) is None


def test_rule_flags_drift_as_advisory():
    features = _features_with_raw(
        [_parm(0, "ATC_RAT_RLL_P", 0.135), _parm(40_000_000, "ATC_RAT_RLL_P", 0.2)]
    )
    result = check_parameter_drift(features, {})
    assert result is not None
    assert result["failure_type"] == "parameter_drift"
    assert result["detection_method"] == "rule"
    assert result["severity"] == "warning"          # tuning-critical
    assert result["confidence"] <= 0.60             # capped, never out-ranks crashes
    assert result["evidence"]


def test_rule_non_critical_change_is_info():
    features = _features_with_raw(
        [_parm(0, "LOG_BITMASK", 100.0), _parm(40_000_000, "LOG_BITMASK", 200.0)]
    )
    result = check_parameter_drift(features, {})
    assert result is not None
    assert result["severity"] == "info"


# --------------------------------------------------------------------------- #
# Engine routing — advisory must NOT pollute the scored crash list
# --------------------------------------------------------------------------- #
def _features_with_drift():
    return _features_with_raw(
        [_parm(0, "ATC_RAT_RLL_P", 0.135), _parm(40_000_000, "ATC_RAT_RLL_P", 0.2)]
    )


def test_rule_engine_routes_drift_to_advisories():
    engine = RuleEngine()
    diagnoses = engine.diagnose(_features_with_drift())
    assert "parameter_drift" not in [d["failure_type"] for d in diagnoses]
    assert "parameter_drift" in [d["failure_type"] for d in engine.advisories]


def test_hybrid_engine_routes_drift_to_advisories():
    engine = HybridEngine()
    diagnoses = engine.diagnose(_features_with_drift())
    assert "parameter_drift" not in [d["failure_type"] for d in diagnoses]
    assert "parameter_drift" in [d["failure_type"] for d in engine.advisories]
    assert "advisories" in engine.last_explain_data


def test_advisory_label_is_not_a_crash_label():
    for label in ADVISORY_LABELS:
        assert label not in VALID_LABELS


# --------------------------------------------------------------------------- #
# Pipeline injection — raw stream stashed, public schema untouched
# --------------------------------------------------------------------------- #
def test_pipeline_stashes_raw_parm_only():
    pipeline = FeaturePipeline()
    parsed = {
        "metadata": {"vehicle_type": "Copter"},
        "messages": {
            "PARM": [
                {"TimeUS": 0, "Name": "ATC_RAT_RLL_P", "Value": 0.135, "mavpackettype": "PARM"},
                {"TimeUS": 40_000_000, "Name": "ATC_RAT_RLL_P", "Value": 0.2, "mavpackettype": "PARM"},
            ]
        },
        "parameters": {},
    }
    features = pipeline.extract(parsed)

    # Public schema untouched.
    public_keys = [k for k in features if not k.startswith("_")]
    assert set(public_keys) == set(FEATURE_NAMES)

    # Raw PARM stream stashed (compact: only TimeUS/Name/Value), detection deferred.
    raw = features["_raw_parm_messages"]
    assert len(raw) == 2
    assert set(raw[0].keys()) == {"TimeUS", "Name", "Value"}

    # And it is detectable through the deferred path.
    assert len(detect_drift_from_features(features)) == 1


def test_pipeline_raw_parm_empty_without_parm():
    pipeline = FeaturePipeline()
    features = pipeline.extract({"messages": {}})
    assert features["_raw_parm_messages"] == []
    assert detect_drift_from_features(features) == []


# --------------------------------------------------------------------------- #
# Advisory findings (CLI/UI shape)
# --------------------------------------------------------------------------- #
def test_drift_findings_shape():
    findings = drift_findings(_features_with_drift())
    assert len(findings) == 1
    f = findings[0]
    assert f["parameter"] == "ATC_RAT_RLL_P"
    assert f["severity"] == "warning"
    assert "ATC_RAT_RLL_P" in f["message"]
    assert "0.135" in f["message"] and "0.2" in f["message"]

"""Tests for in-flight parameter drift detection (issue #39)."""

from src.constants import ADVISORY_LABELS, FEATURE_NAMES, VALID_LABELS
from src.diagnosis.hybrid_engine import HybridEngine
from src.diagnosis.parameter_drift import (
    detect_parameter_drift,
    drift_findings,
    summarize_drift,
)
from src.diagnosis.rule_engine import RuleEngine
from src.diagnosis.rules.parameters import check_parameter_drift
from src.features.pipeline import FeaturePipeline

T0 = 1_000_000


def _parm(t_offset_us, name, value):
    return {"TimeUS": T0 + t_offset_us, "Name": name, "Value": value}


def _base_features():
    return {name: 0.0 for name in FEATURE_NAMES}


# --------------------------------------------------------------------------- #
# Core detector
# --------------------------------------------------------------------------- #
def test_detects_midflight_tuning_change():
    parm = [
        _parm(0, "ATC_RAT_RLL_P", 0.135),
        _parm(40_000_000, "ATC_RAT_RLL_P", 0.200),
    ]
    events = detect_parameter_drift(parm)
    assert len(events) == 1
    ev = events[0]
    assert ev["parameter"] == "ATC_RAT_RLL_P"
    assert ev["old_value"] == 0.135
    assert ev["new_value"] == 0.200
    assert ev["tuning_critical"] is True
    assert ev["t_sec"] == 40.0


def test_boot_dump_changes_are_ignored():
    # Two writes both within the settle window → boot dump, not drift.
    parm = [
        _parm(0, "ATC_RAT_RLL_P", 0.135),
        _parm(1_000_000, "ATC_RAT_RLL_P", 0.140),
    ]
    assert detect_parameter_drift(parm, settle_sec=5.0) == []


def test_auto_learned_and_stat_params_are_ignored():
    parm = [
        _parm(0, "MOT_THST_HOVER", 0.14),
        _parm(40_000_000, "MOT_THST_HOVER", 0.26),   # learned hover throttle
        _parm(0, "STAT_FLTTIME", 500.0),
        _parm(41_000_000, "STAT_FLTTIME", 540.0),    # statistics counter
        _parm(0, "MIS_TOTAL", 4.0),
        _parm(42_000_000, "MIS_TOTAL", 5.0),         # mission housekeeping
    ]
    assert detect_parameter_drift(parm) == []


def test_repeated_identical_value_is_not_a_change():
    parm = [
        _parm(0, "ANGLE_MAX", 4500.0),
        _parm(40_000_000, "ANGLE_MAX", 4500.0),
    ]
    assert detect_parameter_drift(parm) == []


def test_extra_ignore_names_respected():
    parm = [
        _parm(0, "MY_CUSTOM", 1.0),
        _parm(40_000_000, "MY_CUSTOM", 2.0),
    ]
    assert detect_parameter_drift(parm, ignore_names={"MY_CUSTOM"}) == []
    assert len(detect_parameter_drift(parm)) == 1


def test_summary_aggregates_distinct_params_and_onset():
    parm = [
        _parm(0, "ATC_RAT_RLL_P", 0.135),
        _parm(30_000_000, "ATC_RAT_RLL_P", 0.20),
        _parm(0, "ATC_RAT_PIT_P", 0.135),
        _parm(45_000_000, "ATC_RAT_PIT_P", 0.18),
    ]
    events = detect_parameter_drift(parm)
    summary = summarize_drift(events)
    assert summary["count"] == 2.0
    assert summary["tanomaly"] == float(T0 + 30_000_000)
    assert summary["max_rel_change"] > 0.0


def test_empty_input():
    assert detect_parameter_drift(None) == []
    assert detect_parameter_drift([]) == []
    assert summarize_drift([]) == {"count": 0.0, "max_rel_change": 0.0, "tanomaly": -1.0}


# --------------------------------------------------------------------------- #
# Rule
# --------------------------------------------------------------------------- #
def test_rule_returns_none_without_events():
    features = _base_features()
    features["_param_drift_events"] = []
    features["_param_drift_count"] = 0.0
    assert check_parameter_drift(features, {}) is None


def test_rule_flags_drift_as_advisory():
    features = _base_features()
    events = detect_parameter_drift(
        [_parm(0, "ATC_RAT_RLL_P", 0.135), _parm(40_000_000, "ATC_RAT_RLL_P", 0.2)]
    )
    features["_param_drift_events"] = events
    features["_param_drift_count"] = summarize_drift(events)["count"]
    result = check_parameter_drift(features, {})
    assert result is not None
    assert result["failure_type"] == "parameter_drift"
    assert result["detection_method"] == "rule"
    assert result["severity"] == "warning"          # tuning-critical
    assert result["confidence"] <= 0.60              # capped, never out-ranks crashes
    assert result["evidence"]


def test_rule_non_critical_change_is_info():
    features = _base_features()
    events = detect_parameter_drift(
        [_parm(0, "LOG_BITMASK", 100.0), _parm(40_000_000, "LOG_BITMASK", 200.0)]
    )
    features["_param_drift_events"] = events
    features["_param_drift_count"] = summarize_drift(events)["count"]
    result = check_parameter_drift(features, {})
    assert result is not None
    assert result["severity"] == "info"


# --------------------------------------------------------------------------- #
# Engine routing — advisory must NOT pollute the scored crash list
# --------------------------------------------------------------------------- #
def _features_with_drift():
    features = _base_features()
    events = detect_parameter_drift(
        [_parm(0, "ATC_RAT_RLL_P", 0.135), _parm(40_000_000, "ATC_RAT_RLL_P", 0.2)]
    )
    features["_param_drift_events"] = events
    features["_param_drift_count"] = summarize_drift(events)["count"]
    features["_param_drift_max_rel_change"] = summarize_drift(events)["max_rel_change"]
    features["_param_drift_tanomaly"] = summarize_drift(events)["tanomaly"]
    features["_metadata"] = {"vehicle_type": "Copter"}
    return features


def test_rule_engine_routes_drift_to_advisories():
    engine = RuleEngine()
    diagnoses = engine.diagnose(_features_with_drift())
    assert "parameter_drift" not in [d["failure_type"] for d in diagnoses]
    assert "parameter_drift" in [d["failure_type"] for d in engine.advisories]


def test_hybrid_engine_routes_drift_to_advisories():
    engine = HybridEngine()
    diagnoses = engine.diagnose(_features_with_drift())
    assert "parameter_drift" not in [d["failure_type"] for d in diagnoses]
    assert "parameter_drift" in [d["failure_type"] for d in engine.advisories]
    assert "advisories" in engine.last_explain_data


def test_advisory_label_is_not_a_crash_label():
    # parameter_drift must never enter the ML/benchmark crash taxonomy.
    for label in ADVISORY_LABELS:
        assert label not in VALID_LABELS


# --------------------------------------------------------------------------- #
# Pipeline injection — must not disturb the frozen 94-feature schema
# --------------------------------------------------------------------------- #
def test_pipeline_injects_private_drift_keys_only():
    pipeline = FeaturePipeline()
    parsed = {
        "metadata": {"vehicle_type": "Copter"},
        "messages": {
            "PARM": [_parm(0, "ATC_RAT_RLL_P", 0.135), _parm(40_000_000, "ATC_RAT_RLL_P", 0.2)]
        },
        "parameters": {},
    }
    features = pipeline.extract(parsed)
    # Public schema untouched.
    public_keys = [k for k in features if not k.startswith("_")]
    assert set(public_keys) == set(FEATURE_NAMES)
    # Private drift signals present.
    assert features["_param_drift_count"] == 1.0
    assert len(features["_param_drift_events"]) == 1


def test_pipeline_drift_keys_present_even_without_parm():
    pipeline = FeaturePipeline()
    features = pipeline.extract({"messages": {}})
    assert features["_param_drift_count"] == 0.0
    assert features["_param_drift_events"] == []


# --------------------------------------------------------------------------- #
# Advisory findings (CLI/UI shape)
# --------------------------------------------------------------------------- #
def test_drift_findings_shape():
    features = _features_with_drift()
    findings = drift_findings(features)
    assert len(findings) == 1
    f = findings[0]
    assert f["parameter"] == "ATC_RAT_RLL_P"
    assert f["severity"] == "warning"
    assert "ATC_RAT_RLL_P" in f["message"]
    assert "0.135" in f["message"] and "0.2" in f["message"]