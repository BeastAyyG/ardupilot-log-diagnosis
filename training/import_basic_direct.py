"""
BASiC Direct Importer (v2 — filename-based labels)
====================================================
The BASiC dataset labels are embedded in the .BIN filenames:
  e.g. "2022-07-26 18-26-44 (Compass Failure).BIN"

This script walks the extracted folder, parses each filename for its
failure type, copies the .BIN files into the project dataset directory,
and produces a ground_truth.json ready for build_dataset.py.

Usage:
  python training/import_basic_direct.py
  python training/import_basic_direct.py --src "C:/Downloads/BASiC_dataset/extracted/DataFlash Binary Logs" --output "data/clean_imports/basic_dataset"
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# ── Filename keyword → taxonomy label mapping ─────────────────────────────────
KEYWORD_TO_LABEL = {
    "gps failure":           "gps_quality_poor",
    "gps":                   "gps_quality_poor",
    "rc failure":            "rc_failsafe",
    "rc":                    "rc_failsafe",
    "accelerometer failure": "vibration_high",
    "accel":                 "vibration_high",
    "gyro failure":          "vibration_high",
    "gyro":                  "vibration_high",
    "compass failure":       "compass_interference",
    "compass":               "compass_interference",
    "barometer failure":     "ekf_failure",
    "baro failure":          "ekf_failure",
    "barometer":             "ekf_failure",
    "no failure":            "healthy",
    "pre failure":           "healthy",
    "pre-failure":           "healthy",
}


def _parse_label(filename: str) -> str | None:
    """Extract failure type from BASiC filename like '2022-07-26 (Compass Failure).BIN'"""
    # Extract content inside parentheses
    m = re.search(r'\(([^)]+)\)', filename)
    if m:
        inner = m.group(1).strip().lower()
        for keyword, label in KEYWORD_TO_LABEL.items():
            if keyword in inner:
                return label
    # Fallback: search whole filename
    lower_name = filename.lower()
    for keyword, label in KEYWORD_TO_LABEL.items():
        if keyword in lower_name:
            return label
    return None


def _sha256(path: Path, chunk=65536) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk_data := f.read(chunk):
            h.update(chunk_data)
    return h.hexdigest()[:10]


def import_basic_direct(src_dir: Path, output_root: Path) -> dict:
    bin_files = sorted(src_dir.rglob("*.bin")) + sorted(src_dir.rglob("*.BIN"))
    # Exclude .jpg files that accidentally got .bin extension
    bin_files = [b for b in bin_files if b.suffix.lower() == ".bin"]

    print(f"Found {len(bin_files)} .BIN files in {src_dir}")

    dataset_dir = output_root / "dataset"
    dataset_dir.mkdir(parents=True, exist_ok=True)

    labeled_entries = []
    unlabeled = []
    label_counts: dict[str, int] = {}
    seen_hashes: set[str] = set()

    for bf in bin_files:
        label = _parse_label(bf.name)

        # SHA-based dedup (don't import duplicates)
        sha = _sha256(bf)
        if sha in seen_hashes:
            print(f"  SKIP (duplicate): {bf.name}")
            continue
        seen_hashes.add(sha)

        # Unique destination filename: sha prefix + sanitised original name
        safe_name = re.sub(r'[^A-Za-z0-9._-]', '_', bf.name)
        dest = dataset_dir / f"{sha}__{safe_name}"

        shutil.copy2(bf, dest)

        if label:
            labeled_entries.append({
                "filename": dest.name,
                "labels": [label],
                "confidence": "medium",
                "source_type": "BASiC_dataset",
                "trainable": True,
                "sha256_prefix": sha,
                "notes": f"BASiC: {bf.name}"
            })
            label_counts[label] = label_counts.get(label, 0) + 1
        else:
            unlabeled.append(dest.name)
            print(f"  UNLABELED: {bf.name}")

    gt = {"logs": labeled_entries}
    gt_path = output_root / "ground_truth.json"
    gt_path.write_text(json.dumps(gt, indent=2), encoding="utf-8")

    summary = {
        "total_bin": len(bin_files),
        "labeled": len(labeled_entries),
        "unlabeled": len(unlabeled),
        "label_distribution": label_counts,
        "ground_truth": str(gt_path),
        "dataset_dir": str(dataset_dir),
    }

    print("\n" + "=" * 55)
    print("BASiC Direct Import — Complete")
    print("=" * 55)
    print(f"  .BIN files found:   {summary['total_bin']}")
    print(f"  Labeled:            {summary['labeled']}")
    print(f"  Unlabeled:          {summary['unlabeled']}")
    print("\n  Label distribution:")
    for lbl, cnt in sorted(label_counts.items()):
        print(f"    {lbl:<35} {cnt:>3}")
    print(f"\n  Ground truth:  {gt_path}")
    print("\nNext steps:")
    print(f'  python -m training.build_dataset --ground-truth "{gt_path}" --dataset-dir "{dataset_dir}"')
    print("  python -m training.train_model")

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Import BASiC dataset (filename-labeled)")
    parser.add_argument(
        "--src",
        default=r"C:\Downloads\BASiC_dataset\extracted\DataFlash Binary Logs",
        help="Path to the extracted 'DataFlash Binary Logs' folder"
    )
    parser.add_argument(
        "--output",
        default="data/clean_imports/basic_dataset",
        help="Output directory for labeled dataset"
    )
    args = parser.parse_args()

    src = Path(args.src)
    if not src.exists():
        print(f"ERROR: Source folder not found: {src}")
        sys.exit(1)

    output_root = ROOT_DIR / args.output
    import_basic_direct(src, output_root)


if __name__ == "__main__":
    main()
