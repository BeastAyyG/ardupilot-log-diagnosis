"""Safely merge a human-verified clean-import batch into a combined dataset."""

import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_ground_truth(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload.get("logs"), list):
        raise ValueError(f"Ground truth has no logs list: {path}")
    return payload


def merge_verified_batch(
    combined_root: Path,
    batch_root: Path,
    dry_run: bool = False,
) -> dict:
    combined_gt_path = combined_root / "ground_truth.json"
    combined_dataset_dir = combined_root / "dataset"
    batch_gt_path = batch_root / "benchmark_ready" / "ground_truth.json"
    batch_dataset_dir = batch_root / "benchmark_ready" / "dataset"

    combined = _load_ground_truth(combined_gt_path)
    batch = _load_ground_truth(batch_gt_path)

    existing_by_sha: dict[str, dict] = {}
    for entry in combined["logs"]:
        filename = entry.get("filename", "")
        source = combined_dataset_dir / filename
        if not source.is_file():
            continue
        sha256 = entry.get("sha256") or _sha256(source)
        existing_by_sha[sha256] = entry

    prepared = []
    duplicate_count = 0
    for entry in batch["logs"]:
        if entry.get("human_verified") is not True:
            continue
        filename = entry.get("filename", "")
        source = batch_dataset_dir / filename
        if not source.is_file():
            raise FileNotFoundError(f"Verified batch file is missing: {source}")
        sha256 = _sha256(source)
        expected_sha256 = entry.get("sha256", sha256)
        if sha256 != expected_sha256:
            raise ValueError(f"SHA256 mismatch for verified batch file: {source}")

        existing = existing_by_sha.get(sha256)
        if existing is not None:
            if set(existing.get("labels", [])) != set(entry.get("labels", [])):
                raise ValueError(
                    f"Conflicting labels for duplicate SHA256 {sha256}: "
                    f"{existing.get('labels')} vs {entry.get('labels')}"
                )
            duplicate_count += 1
            continue

        destination = combined_dataset_dir / filename
        if destination.exists() and _sha256(destination) != sha256:
            raise ValueError(f"Destination collision: {destination}")
        prepared.append((entry, source, destination, sha256))
        existing_by_sha[sha256] = entry

    result = {
        "added": len(prepared),
        "duplicates": duplicate_count,
        "combined_before": len(combined["logs"]),
        "combined_after": len(combined["logs"]) + len(prepared),
        "dry_run": dry_run,
    }
    if dry_run:
        return result

    combined_dataset_dir.mkdir(parents=True, exist_ok=True)
    for entry, source, destination, sha256 in prepared:
        if not destination.exists():
            shutil.copy2(source, destination)
        combined["logs"].append(
            {
                **entry,
                "filename": destination.name,
                "sha256": sha256,
                "source_type": "human_verified_rule_candidate",
                "trainable": True,
                "human_verified": True,
            }
        )

    temporary_gt = combined_gt_path.with_suffix(".json.tmp")
    with temporary_gt.open("w", encoding="utf-8") as handle:
        json.dump(combined, handle, indent=2)
    os.replace(temporary_gt, combined_gt_path)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Safely merge a human-verified batch into combined_dataset"
    )
    parser.add_argument(
        "--combined-root",
        default="data/combined_dataset",
        help="Combined dataset root containing ground_truth.json and dataset/",
    )
    parser.add_argument(
        "--batch-root",
        required=True,
        help="Clean-import batch root containing benchmark_ready/",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    result = merge_verified_batch(
        combined_root=Path(args.combined_root),
        batch_root=Path(args.batch_root),
        dry_run=args.dry_run,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
