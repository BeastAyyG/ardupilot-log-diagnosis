from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from synthetic_data.readiness_receipt import (
    READINESS_SCHEMA,
    build_readiness_receipt,
    collect_source_snapshot,
    record_command,
    verify_readiness_receipt,
)
from synthetic_data.schema import canonical_json_bytes, sha256_bytes


def _git(root: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _repository(root: Path) -> Path:
    _git(root, "init")
    _git(root, "config", "user.email", "readiness@example.invalid")
    _git(root, "config", "user.name", "Readiness Test")
    (root / "tracked.txt").write_text("version one\n", encoding="utf-8")
    _git(root, "add", "tracked.txt")
    _git(root, "commit", "-m", "fixture")
    return root


def _passing_record(root: Path) -> dict:
    return record_command(root, [sys.executable, "-c", "print('verified')"])


def _rebind(receipt: dict) -> None:
    basis = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    receipt["receipt_sha256"] = sha256_bytes(canonical_json_bytes(basis))


def test_receipt_binds_dirty_source_and_excludes_only_itself(tmp_path) -> None:
    root = _repository(tmp_path)
    (root / "untracked.txt").write_text("evidence\n", encoding="utf-8")
    output = root / "reports" / "readiness.json"

    receipt = build_readiness_receipt(
        root,
        output,
        [_passing_record(root)],
        limitations=["External physical evidence is absent."],
    )
    passed, errors = verify_readiness_receipt(root, output)

    assert passed is True
    assert errors == []
    assert receipt["schema"] == READINESS_SCHEMA
    assert receipt["release_authorized"] is False
    assert receipt["accuracy_gain"] == "not_demonstrated"
    assert receipt["source"]["dirty"] is True
    assert receipt["source"]["excluded_paths"] == ["reports/readiness.json"]
    assert {item["path"] for item in receipt["source"]["entries"]} == {
        "tracked.txt",
        "untracked.txt",
    }


@pytest.mark.parametrize("mutation", ["tracked", "untracked", "staged", "deleted"])
def test_any_source_state_change_invalidates_receipt(tmp_path, mutation) -> None:
    root = _repository(tmp_path)
    output = root / "readiness.json"
    build_readiness_receipt(
        root,
        output,
        [_passing_record(root)],
        limitations=["External evidence absent."],
    )
    if mutation == "tracked":
        (root / "tracked.txt").write_text("changed\n", encoding="utf-8")
    elif mutation == "untracked":
        (root / "new.txt").write_text("new\n", encoding="utf-8")
    elif mutation == "staged":
        (root / "staged.txt").write_text("staged\n", encoding="utf-8")
        _git(root, "add", "staged.txt")
    else:
        (root / "tracked.txt").unlink()

    passed, errors = verify_readiness_receipt(root, output)

    assert passed is False
    assert "current source state differs" in " ".join(errors)


def test_claim_and_content_tampering_fail_even_when_rebound(tmp_path) -> None:
    root = _repository(tmp_path)
    output = root / "readiness.json"
    receipt = build_readiness_receipt(
        root,
        output,
        [_passing_record(root)],
        limitations=["External evidence absent."],
    )
    receipt["release_authorized"] = True
    receipt["accuracy_gain"] = "demonstrated"
    _rebind(receipt)
    output.write_text(json.dumps(receipt), encoding="utf-8")

    passed, errors = verify_readiness_receipt(root, output)

    assert passed is False
    assert "release_authorized" in " ".join(errors)
    assert "required constant" in " ".join(errors)


def test_future_schema_and_failed_command_fail_closed(tmp_path) -> None:
    root = _repository(tmp_path)
    output = root / "readiness.json"
    failed = record_command(root, [sys.executable, "-c", "raise SystemExit(3)"])
    receipt = build_readiness_receipt(
        root,
        output,
        [failed],
        limitations=["External evidence absent."],
    )
    assert verify_readiness_receipt(root, output)[0] is False

    receipt["schema"] = "logdiagnosis.code-readiness-receipt/v99"
    _rebind(receipt)
    output.write_text(json.dumps(receipt), encoding="utf-8")
    passed, errors = verify_readiness_receipt(root, output)

    assert passed is False
    assert errors == ["readiness receipt schema is unsupported"]


def test_snapshot_changes_when_index_changes_without_worktree_change(tmp_path) -> None:
    root = _repository(tmp_path)
    (root / "tracked.txt").write_text("version two\n", encoding="utf-8")
    before = collect_source_snapshot(root)
    _git(root, "add", "tracked.txt")
    after = collect_source_snapshot(root)

    assert before["snapshot_sha256"] != after["snapshot_sha256"]


def test_uninitialized_gitlink_directory_contents_are_bound(tmp_path) -> None:
    root = _repository(tmp_path)
    revision = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    ).stdout.strip()
    _git(root, "update-index", "--add", "--cacheinfo", f"160000,{revision},vendor")
    vendor = root / "vendor"
    vendor.mkdir()
    before = collect_source_snapshot(root)
    (vendor / "local.txt").write_text("dirty nested bytes\n", encoding="utf-8")
    after = collect_source_snapshot(root)

    assert before["snapshot_sha256"] != after["snapshot_sha256"]


def test_gitignored_runtime_telemetry_does_not_destabilize_snapshot(tmp_path) -> None:
    root = _repository(tmp_path)
    (root / ".gitignore").write_text(".runtime/\n", encoding="utf-8")
    _git(root, "add", ".gitignore")
    _git(root, "commit", "-m", "ignore runtime telemetry")
    before = collect_source_snapshot(root)
    runtime = root / ".runtime"
    runtime.mkdir()
    (runtime / "daemon-state.json").write_text('{"tick": 1}\n', encoding="utf-8")
    after = collect_source_snapshot(root)

    assert before == after
