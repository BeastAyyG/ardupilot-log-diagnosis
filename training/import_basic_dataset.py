"""
BASiC Dataset Importer
======================
Extracts the downloaded BASiC dataset .rar file, maps its folder-based
labeling scheme to our ArduPilot taxonomy, then runs the clean_import
pipeline on each flight so they land in:

  data/clean_imports/basic_dataset/benchmark_ready/

Usage:
  python -m training.import_basic_dataset
  python -m training.import_basic_dataset --rar "C:/Downloads/BASiC_dataset/DataFlash_Binary_Logs.rar"

BASiC labeling convention (from paper):
  - Folder named "GPS_Failure"       → gps_quality_poor
  - Folder named "RC_Failure"        → rc_failsafe
  - Folder named "Accel_Failure"     → vibration_high
  - Folder named "Gyro_Failure"      → vibration_high
  - Folder named "Compass_Failure"   → compass_interference
  - Folder named "Baro_Failure"      → ekf_failure
  - Folder named "No_Failure"        → healthy
  - Folder named "Pre_Failure"       → healthy (flight before failure injection)
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import sys
import tempfile
from pathlib import Path

# Ensure project root is on sys.path
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# ── BASiC folder → our label taxonomy ─────────────────────────────────────────
FOLDER_TO_LABEL = {
    "gps":         "gps_quality_poor",
    "gps_failure": "gps_quality_poor",
    "rc":          "rc_failsafe",
    "rc_failure":  "rc_failsafe",
    "accel":       "vibration_high",
    "accel_failure": "vibration_high",
    "gyro":        "vibration_high",
    "gyro_failure": "vibration_high",
    "compass":     "compass_interference",
    "compass_failure": "compass_interference",
    "baro":        "ekf_failure",
    "baro_failure": "ekf_failure",
    "barometer":   "ekf_failure",
    "no_failure":  "healthy",
    "no failure":  "healthy",
    "pre_failure": "healthy",
    "pre failure": "healthy",
    "post_failure": "healthy",   # post-failure flight may have recovered — treat as healthy
}


def _map_label(folder_name: str) -> str | None:
    key = folder_name.strip().lower().replace(" ", "_")
    if key in FOLDER_TO_LABEL:
        return FOLDER_TO_LABEL[key]
    # Fuzzy: if keyword appears in the folder name
    for kw, label in FOLDER_TO_LABEL.items():
        if kw in key:
            return label
    return None


def _extract_rar(rar_path: Path, dest: Path) -> bool:
    """Try to extract the .rar using available tools."""
    dest.mkdir(parents=True, exist_ok=True)

    # Try Python patool (works if 7z or unrar is available on PATH)
    try:
        import patoollib  # noqa: F401 — just to check
    except ImportError:
        pass

    try:
        import patoollib as patool
        patool.extract_archive(str(rar_path), outdir=str(dest))
        return True
    except Exception:
        pass

    # Try patool (the CLI wrapper that calls 7z/unrar/etc)
    try:
        import subprocess
        result = subprocess.run(
            ["patool", "extract", "--outdir", str(dest), str(rar_path)],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            return True
    except Exception:
        pass

    # Try 7z directly
    seven_z = shutil.which("7z") or shutil.which("7za")
    if seven_z:
        import subprocess
        result = subprocess.run(
            [seven_z, "x", str(rar_path), f"-o{dest}", "-y"],
            capture_output=True
        )
        if result.returncode == 0:
            return True

    return False


def import_basic(rar_path: Path, output_root: Path) -> dict:
    """
    Main importer. Extracts the .rar, walks the directory tree, finds .bin
    logs, infers labels from parent folder names, and writes a ground_truth.json
    in the output_root that build_dataset.py can consume.
    """
    print(f"Extracting {rar_path.name} ...")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        ok = _extract_rar(rar_path, tmp_path)

        if not ok:
            print("EXTRACTION FAILED. Do you have 7-Zip or WinRAR installed?")
            print("Install 7-Zip from https://7-zip.org and retry.")
            return {"extracted": False, "reason": "no_rar_tool"}

        # Walk and find all .bin files
        bin_files = list(tmp_path.rglob("*.BIN")) + list(tmp_path.rglob("*.bin"))
        print(f"Found {len(bin_files)} .BIN files")

        labeled_entries = []
        unlabeled = []
        label_counts: dict[str, int] = {}

        dataset_dir = output_root / "dataset"
        dataset_dir.mkdir(parents=True, exist_ok=True)

        for bf in bin_files:
            # Infer label from parent folder hierarchy
            label = None
            for parent in bf.parents:
                label = _map_label(parent.name)
                if label:
                    break

            dest = dataset_dir / bf.name
            # Avoid name collisions with index suffix
            if dest.exists():
                stem, suffix = bf.stem, bf.suffix
                for i in range(1, 999):
                    dest = dataset_dir / f"{stem}_{i}{suffix}"
                    if not dest.exists():
                        break

            shutil.copy2(bf, dest)

            if label:
                labeled_entries.append({
                    "filename": dest.name,
                    "labels": [label],
                    "confidence": "medium",
                    "source_type": "BASiC_dataset",
                    "trainable": True,
                    "notes": f"Auto-labeled from BASiC folder: {bf.parent.name}"
                })
                label_counts[label] = label_counts.get(label, 0) + 1
            else:
                unlabeled.append(dest.name)

    # Write ground_truth.json
    gt = {"logs": labeled_entries}
    gt_path = output_root / "ground_truth.json"
    gt_path.write_text(json.dumps(gt, indent=2), encoding="utf-8")

    summary = {
        "extracted": True,
        "output_root": str(output_root),
        "ground_truth": str(gt_path),
        "total_bin": len(bin_files),
        "labeled": len(labeled_entries),
        "unlabeled": len(unlabeled),
        "label_distribution": label_counts,
    }

    # Print summary
    print("\n" + "=" * 50)
    print(f"BASiC Import Summary")
    print("=" * 50)
    print(f"  Total .BIN files:  {summary['total_bin']}")
    print(f"  Labeled:           {summary['labeled']}")
    print(f"  Unlabeled:         {summary['unlabeled']}")
    print(f"\n  Label distribution:")
    for lbl, cnt in sorted(label_counts.items()):
        print(f"    {lbl:<30} {cnt:>4}")
    print(f"\n  Ground truth:  {gt_path}")
    print(f"\nNext steps:")
    print(f"  python -m training.build_dataset --ground-truth \"{gt_path}\" --dataset-dir \"{dataset_dir}\"")
    print(f"  python -m training.train_model")

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Import BASiC dataset into ArduPilot training pipeline")
    parser.add_argument("--rar", default="C:/Downloads/BASiC_dataset/DataFlash_Binary_Logs.rar",
                        help="Path to the DataFlash Binary Logs.rar file")
    parser.add_argument("--output", default="data/clean_imports/basic_dataset",
                        help="Output directory for labeled dataset")
    args = parser.parse_args()

    rar_path = Path(args.rar)
    if not rar_path.exists():
        print(f"ERROR: .rar file not found at {rar_path}")
        print("Is the download still running? Check with:")
        print("  Get-BitsTransfer")
        sys.exit(1)

    output_root = ROOT_DIR / args.output
    import_basic(rar_path, output_root)


if __name__ == "__main__":
    main()
