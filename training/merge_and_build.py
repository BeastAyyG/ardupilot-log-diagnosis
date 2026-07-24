import os
import json
import shutil
from pathlib import Path


def main():
    root_dir = Path(__file__).resolve().parents[1]
    combined_dir = root_dir / "data" / "combined_dataset"
    combined_logs_dir = combined_dir / "dataset"

    # Clean and recreate combined folders
    if combined_dir.exists():
        shutil.rmtree(combined_dir)
    os.makedirs(combined_logs_dir, exist_ok=True)

    # 1. Source 1: basic_dataset
    basic_gt_path = root_dir / "data" / "clean_imports" / "basic_dataset" / "ground_truth.json"
    basic_logs_dir = root_dir / "data" / "clean_imports" / "basic_dataset" / "dataset"

    with open(basic_gt_path, "r", encoding="utf-8") as f:
        basic_gt = json.load(f)

    # 2. Source 2: Kaggle logs
    kaggle_gt_path = root_dir / "data" / "kaggle_backups" / "ardupilot-master-log-pool-v2" / "ground_truth.json"
    kaggle_logs_dir = root_dir / "data" / "kaggle_backups" / "ardupilot-master-log-pool-v2"

    with open(kaggle_gt_path, "r", encoding="utf-8") as f:
        kaggle_gt = json.load(f)

    combined_logs = []

    # Copy basic logs and collect entries
    print(f"Copying {len(basic_gt['logs'])} basic_dataset logs...")
    for log in basic_gt["logs"]:
        filename = log["filename"]
        src = basic_logs_dir / filename
        dst = combined_logs_dir / filename
        if src.exists():
            shutil.copy2(src, dst)
            combined_logs.append(log)

    # Copy Kaggle logs and collect entries
    print(f"Copying {len(kaggle_gt['logs'])} Kaggle master pool logs...")
    for log in kaggle_gt["logs"]:
        filename = log["filename"]
        src = kaggle_logs_dir / filename
        dst = combined_logs_dir / filename
        if src.exists():
            shutil.copy2(src, dst)
            combined_logs.append(log)

    combined_gt = {
        "metadata": {
            "description": "Combined dataset containing clean simulated basic dataset and real-world Kaggle logs"
        },
        "logs": combined_logs
    }

    combined_gt_path = combined_dir / "ground_truth.json"
    with open(combined_gt_path, "w", encoding="utf-8") as f:
        json.dump(combined_gt, f, indent=2)

    print(f"Dataset files merged. Total log entries: {len(combined_logs)}")
    print(f"Unified ground_truth.json written to: {combined_gt_path}")
    print(f"Unified logs copied to: {combined_logs_dir}")


if __name__ == "__main__":
    main()
