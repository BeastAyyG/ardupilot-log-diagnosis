"""Tests for the real-log benchmark registry and paper evaluation helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from training.build_incident_registry import evidence_for, incident_id_for, verify_seal
from training.paper_eval import NO_DIAGNOSIS, cluster_bootstrap, macro_f1, summarise

ROOT = Path(__file__).resolve().parents[1]


def test_incident_id_groups_by_thread_not_attachment():
    slug = "https://discuss.ardupilot.org/t/crash-with-4-0-0-rc3/50267"
    assert incident_id_for(slug) == "discuss:50267"
    assert incident_id_for(slug + "/12") == "discuss:50267"
    assert incident_id_for("https://github.com/ArduPilot/ardupilot/issues/8931") == (
        "github:issues:8931"
    )
    assert incident_id_for(
        "https://drive.google.com/drive/folders/152GnHaxx?usp=sharing"
    ) == "gdrive:152GnHaxx"
    assert incident_id_for("") == ""


def test_committed_cohort_manifest_seal_verifies():
    manifest = json.loads((ROOT / "data/cohorts/cohort_manifest.json").read_text())
    assert verify_seal(manifest) == manifest["seal"]["content_sha256"]


def test_tampered_manifest_is_rejected():
    manifest = json.loads((ROOT / "data/cohorts/cohort_manifest.json").read_text())
    manifest["description"] = "tampered"
    with pytest.raises(ValueError):
        verify_seal(manifest)


def test_evidence_tier_prefers_named_quote_then_summary():
    notes = {
        "a": [{"quote": "summary", "username": "", "sha256": "", "source": "x"}],
        "b": [
            {"quote": "summary", "username": "", "sha256": "", "source": "x"},
            {"quote": "diagnosis", "username": "dev", "sha256": "", "source": "y"},
        ],
    }
    assert evidence_for("a", notes)[0] == "author_summary"
    assert evidence_for("b", notes)[:3] == ("named_user_quote", "diagnosis", "dev")
    assert evidence_for("c", notes)[0] == "none"


def test_registry_excludes_conflicts_and_contradicted_labels():
    rows = (ROOT / "data/benchmark/incidents.csv").read_text().splitlines()
    header = rows[0].split(",")
    assert {"incident_id", "evaluable", "exclusion_reason", "evidence_tier"} <= set(header)
    ground_truth = json.loads((ROOT / "data/benchmark/ground_truth_real_v1.json").read_text())
    incidents = {entry["incident_id"] for entry in ground_truth["logs"]}
    assert "discuss:50267" not in incidents  # conflicting labels
    assert "discuss:101680" not in incidents  # label contradicted by its source
    assert all(len(entry["labels"]) == 1 for entry in ground_truth["logs"])


def test_rule_derived_labels_are_reverted():
    ground_truth = json.loads((ROOT / "data/benchmark/ground_truth_real_v1.json").read_text())
    by_key = {entry["filename"][:10]: entry["labels"][0] for entry in ground_truth["logs"]}
    assert by_key.get("0818fe7e5c") == "rc_failsafe"
    assert by_key.get("b89fc87fea") == "rc_failsafe"


def test_macro_f1_ignores_classes_absent_from_truth():
    assert macro_f1(["a", "a", "b"], ["a", "a", "b"]) == 1.0
    # A wrong prediction of an absent class lowers recall, not an extra column.
    assert macro_f1(["a", "b"], ["a", "c"]) == pytest.approx(0.5)


def test_cluster_bootstrap_resamples_whole_incidents():
    truth = ["a", "a", "b", "b"]
    pred = ["a", "a", "b", "b"]
    ci = cluster_bootstrap(truth, pred, ["i1", "i1", "i2", "i2"], macro_f1)
    assert ci["low"] == ci["high"] == 1.0


def test_summarise_reports_coverage_and_per_class_recall():
    result = summarise(["a", "b"], ["a", NO_DIAGNOSIS], ["i1", "i2"])
    assert result["coverage"] == 0.5
    assert result["per_class"]["a"]["recall"] == 1.0
    assert result["per_class"]["b"]["recall"] == 0.0
