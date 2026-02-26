#!/usr/bin/env python3
"""Recover and verify the Kaggle master-pool backup dataset."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def _run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout


def _count_bins(folder: Path) -> int:
    return sum(1 for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".bin")


def _load_gt_count(path: Path) -> int:
    if not path.exists():
        return 0
    payload = json.loads(path.read_text(encoding="utf-8"))
    return len(payload.get("logs", []))


def _sync_to_master_pool(src_dir: Path, master_pool_dir: Path) -> dict:
    dataset_dir = master_pool_dir / "dataset"
    dataset_dir.mkdir(parents=True, exist_ok=True)

    copied = 0
    skipped = 0
    for src in src_dir.iterdir():
        if not src.is_file() or src.suffix.lower() != ".bin":
            continue
        dst = dataset_dir / src.name
        if dst.exists():
            skipped += 1
            continue
        shutil.copy2(src, dst)
        copied += 1

    gt_src = src_dir / "ground_truth.json"
    gt_dst = master_pool_dir / "ground_truth.json"
    gt_copied = False
    if gt_src.exists():
        shutil.copy2(gt_src, gt_dst)
        gt_copied = True

    return {
        "copied_bin_files": copied,
        "skipped_existing_bin_files": skipped,
        "ground_truth_copied": gt_copied,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync Kaggle master-pool backup")
    parser.add_argument(
        "--dataset-ref",
        default="beastayyg/ardupilot-master-log-pool-v2",
        help="Kaggle dataset reference <owner>/<dataset>",
    )
    parser.add_argument(
        "--output-dir",
        default="data/kaggle_backups/ardupilot-master-log-pool-v2",
        help="Folder where Kaggle files will be downloaded",
    )
    parser.add_argument(
        "--expected-log-count",
        type=int,
        default=45,
        help="Expected number of .bin files",
    )
    parser.add_argument(
        "--sync-master-pool",
        action="store_true",
        help="Also sync downloaded files into data/master_pool",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    files_csv = _run([
        "kaggle",
        "datasets",
        "files",
        args.dataset_ref,
        "--page-size",
        "200",
        "-v",
    ])

    _run(
        [
            "kaggle",
            "datasets",
            "download",
            "-d",
            args.dataset_ref,
            "-p",
            str(output_dir),
            "-o",
            "--unzip",
        ]
    )

    bin_count = _count_bins(output_dir)
    gt_path = output_dir / "ground_truth.json"
    gt_count = _load_gt_count(gt_path)

    sync_report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_ref": args.dataset_ref,
        "output_dir": str(output_dir),
        "expected_log_count": args.expected_log_count,
        "observed_log_count": bin_count,
        "ground_truth_path": str(gt_path),
        "ground_truth_count": gt_count,
        "validation": {
            "log_count_ok": bin_count == args.expected_log_count,
            "ground_truth_count_ok": gt_count == args.expected_log_count,
        },
        "artifacts": {
            "kaggle_files_csv": str(output_dir / "kaggle_files.csv"),
            "report_json": str(output_dir / "kaggle_sync_report.json"),
        },
    }

    master_sync = None
    if args.sync_master_pool:
        master_sync = _sync_to_master_pool(output_dir, Path("data/master_pool"))
        sync_report["master_pool_sync"] = master_sync

    (output_dir / "kaggle_files.csv").write_text(files_csv, encoding="utf-8")
    (output_dir / "kaggle_sync_report.json").write_text(
        json.dumps(sync_report, indent=2) + "\n",
        encoding="utf-8",
    )

    print("Kaggle sync complete")
    print(f"dataset_ref={args.dataset_ref}")
    print(f"output_dir={output_dir}")
    print(f"observed_log_count={bin_count}")
    print(f"ground_truth_count={gt_count}")
    print(f"log_count_ok={sync_report['validation']['log_count_ok']}")
    print(f"ground_truth_count_ok={sync_report['validation']['ground_truth_count_ok']}")
    if master_sync is not None:
        print(f"master_pool_copied_bin_files={master_sync['copied_bin_files']}")
        print(f"master_pool_skipped_existing_bin_files={master_sync['skipped_existing_bin_files']}")


if __name__ == "__main__":
    main()
