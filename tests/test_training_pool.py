import hashlib
import json
import sys

import pytest

from training.build_real_training_pool import (
    _collect_manual_candidates,
    _collect_verified_candidates,
    _index_backup_files,
    main,
)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def test_verified_log_can_be_recovered_from_external_backup(tmp_path):
    clean_root = tmp_path / "clean_imports"
    manifest_dir = clean_root / "batch_a" / "manifests"
    manifest_dir.mkdir(parents=True)

    payload = b"verified-flight"
    file_name = "flight.bin"
    manifest = [
        {
            "category": "verified_labeled",
            "file_name": file_name,
            "source_path": f"downloads/{file_name}",
            "sha256": _sha256(payload),
            "mapped_label": "vibration_high",
            "source_type": "test",
        }
    ]
    (manifest_dir / "clean_import_manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )

    backup_file = (
        tmp_path
        / "backup"
        / "clean_imports"
        / "batch_a"
        / "benchmark_ready"
        / "dataset"
        / file_name
    )
    backup_file.parent.mkdir(parents=True)
    backup_file.write_bytes(payload)

    stats = {}
    index = _index_backup_files([tmp_path / "backup"])
    candidates = _collect_verified_candidates(
        clean_root,
        set(),
        backup_index=index,
        stats=stats,
    )

    assert len(candidates) == 1
    assert candidates[0]["src_file"] == backup_file
    assert stats["missing_verified_files"] == 0


def test_manual_log_resolves_sha_prefixed_backup_name(tmp_path):
    manual_dir = tmp_path / "manual"
    manual_dir.mkdir()
    (manual_dir / "ground_truth.json").write_text(
        json.dumps(
            {
                "flight.BIN": {
                    "label": "power_instability",
                    "confidence": "high",
                    "source": "manual_review",
                }
            }
        ),
        encoding="utf-8",
    )

    backup_file = tmp_path / "backup" / "abc123__flight.BIN"
    backup_file.parent.mkdir()
    backup_file.write_bytes(b"manual-flight")

    stats = {}
    candidates = _collect_manual_candidates(
        manual_dir / "ground_truth.json",
        backup_index=_index_backup_files([tmp_path / "backup"]),
        stats=stats,
    )

    assert len(candidates) == 1
    assert candidates[0]["src_file"] == backup_file
    assert stats["missing_manual_files"] == 0


def test_empty_rebuild_refuses_to_delete_existing_output(tmp_path, monkeypatch):
    output_root = tmp_path / "existing"
    output_root.mkdir()
    marker = output_root / "keep.txt"
    marker.write_text("preserve me", encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_real_training_pool.py",
            "--clean-import-root",
            str(tmp_path / "missing"),
            "--manual-ground-truth",
            str(tmp_path / "missing-ground-truth.json"),
            "--output-root",
            str(output_root),
        ],
    )

    with pytest.raises(SystemExit, match="refusing to replace"):
        main()

    assert marker.read_text(encoding="utf-8") == "preserve me"
