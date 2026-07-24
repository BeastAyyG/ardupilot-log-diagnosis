"""
promote_verified_labels.py

Reads provisional_auto_labels_*.json, picks up all entries where
human_verified=True, and writes a clean ground_truth.json + dataset/
folder structure ready to feed into build_dataset.py.

Usage:
    python3 training/promote_verified_labels.py \\
        --provisional data/to_label/provisional_auto_labels_2026-03-01.json \\
        --output-dir  data/clean_imports/human_review_batch_01/

Human-approved .BIN files are copied into benchmark_ready/dataset with a
SHA-prefixed filename so build_dataset.py can consume the batch directly.
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def promote(provisional_path: str, output_dir: str, dry_run: bool = False) -> dict:
    if not os.path.exists(provisional_path):
        print(f"ERROR: {provisional_path} not found")
        sys.exit(1)

    with open(provisional_path) as f:
        data = json.load(f)

    logs = data.get("logs", [])
    print(f"Provisional file: {provisional_path}")
    print(f"Total entries:    {len(logs)}")

    verified = [
        log_entry for log_entry in logs
        if log_entry.get("human_verified") is True
        and log_entry.get("auto_label")
        and log_entry.get("status", "").startswith("auto_labeled")
    ]
    skipped = len(logs) - len(verified)

    print(f"Verified entries: {len(verified)}")
    print(f"Skipped (unverified/failed): {skipped}")

    if not verified:
        print("\nNothing to promote. Set human_verified=True on entries you approve.")
        return {"promoted": 0, "skipped": skipped}

    if dry_run:
        print("\n[DRY RUN] Would promote:")
        for entry in verified:
            print(
                f"  {entry['filename']} -> {entry['auto_label']} "
                f"({entry['confidence'] * 100:.0f}%)"
            )
        return {"promoted": len(verified), "skipped": skipped, "dry_run": True}

    prepared = []
    for entry in verified:
        source_path = entry.get("path", "")
        if not os.path.isfile(source_path):
            raise FileNotFoundError(
                f"Verified candidate source is missing: {source_path!r}"
            )
        sha256 = entry.get("sha256") or _sha256(source_path)
        if _sha256(source_path) != sha256:
            raise ValueError(
                f"SHA256 mismatch for verified candidate: {source_path}"
            )
        safe_name = os.path.basename(entry["filename"])
        promoted_name = f"{sha256[:10]}__{safe_name}"
        prepared.append((entry, source_path, sha256, promoted_name))

    # Build output structure
    bmark_dir = os.path.join(output_dir, "benchmark_ready")
    dataset_dir = os.path.join(bmark_dir, "dataset")
    manifest_dir = os.path.join(output_dir, "manifests")
    os.makedirs(dataset_dir, exist_ok=True)
    os.makedirs(manifest_dir, exist_ok=True)

    # Build ground_truth.json entries
    gt_logs = []
    manifest_rows = []
    for entry, source_path, sha256, promoted_name in prepared:
        destination = os.path.join(dataset_dir, promoted_name)
        if os.path.exists(destination):
            if _sha256(destination) != sha256:
                raise ValueError(
                    f"Destination collision with different content: {destination}"
                )
        else:
            shutil.copy2(source_path, destination)

        gt_logs.append({
            "filename": promoted_name,
            "labels": [entry["auto_label"]],
            "label": entry["auto_label"],
            "confidence": "high" if entry["confidence"] >= 0.75 else "medium",
            "source_type": "human_verified_rule_candidate",
            "trainable": True,
            "human_verified": True,
            "sha256": sha256,
            "auto_label_confidence": entry["confidence"],
            "engine": entry.get("engine"),
            "evidence": entry.get("evidence", []),
            "notes": entry.get("notes", ""),
            "promoted_from": provisional_path,
            "promoted_at_utc": datetime.now(timezone.utc).isoformat(),
            # Keep published provenance portable and avoid embedding a
            # contributor's absolute filesystem path in generated metadata.
            "original_path": os.path.basename(source_path),
        })
        manifest_rows.append(
            {
                "category": "verified_labeled",
                "file_name": promoted_name,
                "source_path": os.path.join(
                    "benchmark_ready", "dataset", promoted_name
                ),
                "sha256": sha256,
                "mapped_label": entry["auto_label"],
                "source_url": entry.get("expert_source", ""),
                "source_type": "human_verified_rule_candidate",
                "expert_quote": entry.get("notes", ""),
            }
        )

    gt_path = os.path.join(bmark_dir, "ground_truth.json")
    with open(gt_path, "w") as f:
        json.dump({"logs": gt_logs}, f, indent=2)

    print(f"\nWrote: {gt_path} ({len(gt_logs)} entries)")

    clean_manifest_path = os.path.join(
        manifest_dir, "clean_import_manifest.json"
    )
    with open(clean_manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_rows, f, indent=2)
    print(f"Wrote: {clean_manifest_path}")

    # Write a human-readable import summary
    summary = {
        "source_provisional": provisional_path,
        "promoted_at_utc": datetime.now(timezone.utc).isoformat(),
        "total_in_provisional": len(logs),
        "promoted": len(verified),
        "skipped": skipped,
        "label_distribution": {},
    }
    dist = Counter(e["auto_label"] for e in verified)
    summary["label_distribution"] = dict(sorted(dist.items(), key=lambda x: -x[1]))

    summary_path = os.path.join(manifest_dir, "import_summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"Wrote: {summary_path}")

    print("\nPromotion complete.")
    print(
        "   Batch is buildable with "
        f"--ground-truth {bmark_dir}/ground_truth.json "
        f"--dataset-dir {dataset_dir}"
    )
    print(
        "   Merge this reviewed batch into the main training pool before "
        "retraining; do not train on the small batch alone."
    )

    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Promote human-verified auto-labels to a training batch"
    )
    parser.add_argument(
        "--provisional",
        required=True,
        help="Path to provisional_auto_labels_*.json",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Output directory (will create benchmark_ready/ and manifests/ inside)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be promoted without writing anything",
    )
    args = parser.parse_args()
    promote(args.provisional, args.output_dir, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
