"""Tests for training/build_benchmark_v4.py.

These use synthetic annotations and a synthetic .bin so they validate the merge
/ conflict / hash logic without touching the real benchmark data. They do NOT
assert anything about real incident counts.
"""

import hashlib
import json
import sys
from pathlib import Path

import pytest

from training.build_benchmark_v4 import main as build_v4


def _fake_bin(path, payload: bytes = b"fake-log-bytes") -> Path:
    path.write_bytes(payload)
    return path


def _sha(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_v3(base_path, logs):
    doc = {"schema": "v3", "label_policy": "thread", "logs": logs}
    base_path.write_text(json.dumps(doc))


def _write_v4_annotations(path, records):
    doc = {"schema": "pool-v4", "records": records}
    path.write_text(json.dumps(doc))


@pytest.fixture
def work(tmp_path):
    pool = tmp_path / "pool"
    pool.mkdir()
    stage = tmp_path / "stage"
    base = tmp_path / "v3.json"
    v4 = tmp_path / "v4.json"

    b1 = _sha(_fake_bin(pool / "a.BIN"))
    b2 = _sha(_fake_bin(pool / "b.BIN"))

    # v3 base: two incidents
    _write_v3(
        base,
        [
            {"filename": "v3x.BIN", "labels": ["vibration_high"], "incident_id": "discuss:1",
             "sha256": "0" * 64, "certainty": "explicit", "origin": "v3"},
            {"filename": "v3y.BIN", "labels": ["ekf_failure"], "incident_id": "discuss:2",
             "sha256": "1" * 64, "certainty": "explicit", "origin": "v3"},
        ],
    )
    # v4 new incidents
    _write_v4_annotations(
        v4,
        [
            {"status": "labelled", "thread": "discuss:3", "label": "gps_quality_poor",
             "certainty": "explicit", "diagnosing_post": "u/3", "source_url": "u",
             "files": [{"file": "a.BIN", "sha256": b1}], "log_key": "a"},
            {"status": "labelled", "thread": "discuss:4", "label": "brownout",
             "certainty": "tentative", "diagnosing_post": "u/4", "source_url": "u",
             "files": [{"file": "b.BIN", "sha256": b2}], "log_key": "b"},
            # already in base -> skipped
            {"status": "labelled", "thread": "discuss:1", "label": "vibration_high",
             "certainty": "explicit", "diagnosing_post": "u", "source_url": "u",
             "files": [{"file": "x.BIN", "sha256": "0" * 64}], "log_key": "x"},
            # not labelled -> skipped
            {"status": "undiagnosed", "thread": "discuss:5", "label": "",
             "certainty": "", "diagnosing_post": "u", "source_url": "u",
             "files": [{"file": "c.BIN", "sha256": "0" * 64}], "log_key": "c"},
        ],
    )
    return {"base": base, "v4": v4, "pool": pool, "stage": stage,
            "out": tmp_path / "out.json", "summary": tmp_path / "summary.json"}


def _run(work):
    sys.argv = [
        "build_benchmark_v4.py",
        "--base", str(work["base"]), "--v4", str(work["v4"]),
        "--pool-dir", str(work["pool"]), "--stage-dir", str(work["stage"]),
        "--output", str(work["out"]),
    ]
    return build_v4()


def test_v4_merges_and_skips(work):
    rc = _run(work)
    assert rc == 0
    doc = json.loads(work["out"].read_text())
    inc_ids = {e["incident_id"] for e in doc["logs"]}
    # v3's 2 + v4's 2 new (3 and 4); 1 is deduped, 5 is undiagnosed
    assert inc_ids == {"discuss:1", "discuss:2", "discuss:3", "discuss:4"}
    assert doc["schema"] == "logdiagnosis.real-benchmark-ground-truth/v4"
    assert doc["frozen_protocol"].endswith("PREREGISTRATION_V4.md")


def test_conflicted_incident_dropped(work):
    # add a second label to an existing incident in v3 -> conflicted drop
    base = json.loads(work["base"].read_text())
    base["logs"].append({"filename": "v3z.BIN", "labels": ["thrust_loss"],
                         "incident_id": "discuss:1", "sha256": "2" * 64,
                         "certainty": "explicit", "origin": "v3"})
    work["base"].write_text(json.dumps(base))
    _run(work)
    doc = json.loads(work["out"].read_text())
    # discuss:1 now has two labels -> entire incident dropped
    assert "discuss:1" not in {e["incident_id"] for e in doc["logs"]}


def test_missing_annotations_file_is_a_clear_error(tmp_path):
    missing = tmp_path / "nope.json"
    sys.argv = ["build_benchmark_v4.py", "--v4", str(missing)]
    rc = build_v4()
    assert rc == 2  # documents the maintainer step instead of inventing labels
