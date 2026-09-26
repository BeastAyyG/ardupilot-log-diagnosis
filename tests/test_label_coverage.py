"""Milestone 3 "done when": every ``VALID_LABEL`` must have a reachable path.

``docs/UPGRADE_ROADMAP.md`` closes Milestone 3 only when *all 14*
``VALID_LABELS`` have at least one rule or ML path that can trigger them.

Two things are pinned here:

1. **Coverage** — no label is dead. The union of rule-emittable labels and
   ML-predictable labels must cover ``VALID_LABELS``.
2. **Honesty about the split** — the ML classifier can only predict 6 of the
   14 labels. The remaining 8 are *rules-only*. That set is asserted, not just
   described, so a reader cannot assume a rules-only label has ML support, and
   changing the set is a deliberate, reviewable act.

Emission itself is proven per-rule by ``tests/test_diagnosis_rules.py``, which
drives each rule across its threshold boundaries.
"""

import json

from src.constants import FEATURE_NAMES, VALID_LABELS
from src.runtime_paths import MODELS_DIR

RULES_DIR = MODELS_DIR.parent / "src" / "diagnosis" / "rules"

# Label(s) each rule module can emit. ``power`` and ``motors`` emit more than
# one label depending on which evidence branch fires.
RULE_MODULE_LABELS: dict[str, set[str]] = {
    "compass": {"compass_interference"},
    "crash_unknown": {"crash_unknown"},
    "ekf": {"ekf_failure"},
    "gps": {"gps_quality_poor"},
    "mechanical_failure": {"mechanical_failure"},
    "motors": {"motor_imbalance", "pid_tuning_issue"},
    "pid_tuning": {"pid_tuning_issue"},
    "power": {"power_instability", "brownout"},
    "rc_failsafe": {"rc_failsafe"},
    "setup_error": {"setup_error"},
    "system": {"mechanical_failure"},
    "thrust_loss": {"thrust_loss"},
    "vibration": {"vibration_high"},
}

# The 8 labels with no ML path. Kept explicit so the delegation is obvious.
RULES_ONLY_LABELS = {
    "brownout",
    "crash_unknown",
    "mechanical_failure",
    "motor_imbalance",
    "pid_tuning_issue",
    "power_instability",
    "setup_error",
    "thrust_loss",
}


def _rule_module_names() -> set[str]:
    return {path.stem for path in RULES_DIR.glob("*.py") if path.stem != "__init__"}


def _ml_labels() -> set[str]:
    return set(json.loads((MODELS_DIR / "label_columns.json").read_text(encoding="utf-8")))


def _rule_labels() -> set[str]:
    return {label for labels in RULE_MODULE_LABELS.values() for label in labels}


def test_every_rule_module_declares_the_labels_it_can_emit():
    """A newly added rule module must declare coverage instead of slipping through."""
    assert _rule_module_names() == set(RULE_MODULE_LABELS)


def test_every_valid_label_is_reachable_by_a_rule_or_the_ml_model():
    unreachable = set(VALID_LABELS) - (_rule_labels() | _ml_labels())
    assert unreachable == set(), f"no rule or ML path can trigger: {sorted(unreachable)}"


def test_ml_never_predicts_a_label_outside_valid_labels():
    unknown = _ml_labels() - set(VALID_LABELS)
    assert unknown == set(), f"model predicts labels outside VALID_LABELS: {sorted(unknown)}"


def test_rules_only_labels_match_the_documented_set():
    """These eight have no ML path; the rule engine is the only thing that can
    raise them. Confidences for these labels come from rules alone and are not
    calibrated by the ML layer."""
    assert set(VALID_LABELS) - _ml_labels() == RULES_ONLY_LABELS


def test_declared_labels_actually_appear_in_the_rule_module_source():
    """Cheap drift guard: a declared label must exist as a literal in the module."""
    for module_name, labels in RULE_MODULE_LABELS.items():
        source = (RULES_DIR / f"{module_name}.py").read_text(encoding="utf-8")
        for label in labels:
            assert f'"{label}"' in source, f"{module_name}.py never mentions {label!r}"


def test_model_feature_columns_are_a_subset_of_runtime_features():
    """The model scores a 94-column subset of the 111 runtime features."""
    model_columns = json.loads((MODELS_DIR / "feature_columns.json").read_text(encoding="utf-8"))
    assert len(model_columns) == 94
    assert set(model_columns) <= set(FEATURE_NAMES)
