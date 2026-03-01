"""
promote_verified_labels.py

Reads provisional_auto_labels_*.json, picks up all entries where
human_verified=True, and writes a clean ground_truth.json + dataset/
folder structure ready to feed into build_dataset.py.

Usage:
    python3 training/promote_verified_labels.py \\
        --provisional data/to_label/provisional_auto_labels_2026-03-01.json \\
        --output-dir  data/clean_imports/human_review_batch_01/

The .BIN files themselves are NOT copied (they stay in the Kaggle cache).
The output ground_truth.json will use the original _path from the provisional
file so build_dataset.py can find them.
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone


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
        l for l in logs
        if l.get("human_verified") is True
        and l.get("auto_label")
        and l.get("status", "").startswith("auto_labeled")
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
            print(f"  {entry['filename']}  →  {entry['auto_label']}  ({entry['confidence']*100:.0f}%)")
        return {"promoted": len(verified), "skipped": skipped, "dry_run": True}

    # Build output structure
    bmark_dir = os.path.join(output_dir, "benchmark_ready")
    manifest_dir = os.path.join(output_dir, "manifests")
    os.makedirs(bmark_dir, exist_ok=True)
    os.makedirs(manifest_dir, exist_ok=True)

    # Build ground_truth.json entries
    gt_logs = []
    for entry in verified:
        gt_logs.append({
            "filename": entry["filename"],
            "labels": [entry["auto_label"]],
            "label": entry["auto_label"],
            "confidence": "high" if entry["confidence"] >= 0.75 else "medium",
            "source_type": "hybrid_engine_auto_labeled",
            "trainable": True,
            "human_verified": True,
            "auto_label_confidence": entry["confidence"],
            "engine": entry.get("engine"),
            "evidence": entry.get("evidence", []),
            "notes": entry.get("notes", ""),
            "promoted_from": provisional_path,
            "promoted_at_utc": datetime.now(timezone.utc).isoformat(),
            # Keep original path reference so build_dataset.py can find the .bin
            "_original_path": entry.get("path", ""),
        })

    gt_path = os.path.join(bmark_dir, "ground_truth.json")
    with open(gt_path, "w") as f:
        json.dump({"logs": gt_logs}, f, indent=2)

    print(f"\nWrote: {gt_path} ({len(gt_logs)} entries)")

    # Write a human-readable import summary
    summary = {
        "source_provisional": provisional_path,
        "promoted_at_utc": datetime.now(timezone.utc).isoformat(),
        "total_in_provisional": len(logs),
        "promoted": len(verified),
        "skipped": skipped,
        "label_distribution": {},
    }
    from collections import Counter
    dist = Counter(e["auto_label"] for e in verified)
    summary["label_distribution"] = dict(sorted(dist.items(), key=lambda x: -x[1]))

    summary_path = os.path.join(manifest_dir, "import_summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"Wrote: {summary_path}")

    print("\n✅ Promotion complete.")
    print(f"   Next: run build_dataset.py pointing at {bmark_dir}/ground_truth.json")
    print( "   Then: python3 training/train_model.py")

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
