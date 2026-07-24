import json
from pathlib import Path

from training.merge_verified_batch import _sha256, merge_verified_batch


def _write_ground_truth(path: Path, logs: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"logs": logs}), encoding="utf-8")


def test_merge_verified_batch_is_deduplicated_and_non_destructive(tmp_path):
    combined_root = tmp_path / "combined"
    combined_dataset = combined_root / "dataset"
    combined_dataset.mkdir(parents=True)
    existing = combined_dataset / "existing.bin"
    existing.write_bytes(b"existing")
    existing_sha = _sha256(existing)
    _write_ground_truth(
        combined_root / "ground_truth.json",
        [
            {
                "filename": existing.name,
                "sha256": existing_sha,
                "labels": ["healthy"],
            }
        ],
    )

    batch_root = tmp_path / "batch"
    batch_dataset = batch_root / "benchmark_ready" / "dataset"
    batch_dataset.mkdir(parents=True)
    new_log = batch_dataset / "new.bin"
    new_log.write_bytes(b"new verified flight")
    new_sha = _sha256(new_log)
    _write_ground_truth(
        batch_root / "benchmark_ready" / "ground_truth.json",
        [
            {
                "filename": new_log.name,
                "sha256": new_sha,
                "labels": ["motor_imbalance"],
                "human_verified": True,
            }
        ],
    )

    dry_run = merge_verified_batch(combined_root, batch_root, dry_run=True)
    assert dry_run["added"] == 1
    assert not (combined_dataset / "new.bin").exists()

    result = merge_verified_batch(combined_root, batch_root)
    repeated = merge_verified_batch(combined_root, batch_root)
    merged = json.loads(
        (combined_root / "ground_truth.json").read_text(encoding="utf-8")
    )

    assert result["added"] == 1
    assert repeated["added"] == 0
    assert repeated["duplicates"] == 1
    assert existing.read_bytes() == b"existing"
    assert (combined_dataset / "new.bin").read_bytes() == b"new verified flight"
    assert len(merged["logs"]) == 2
