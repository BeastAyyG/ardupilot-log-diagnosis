#!/usr/bin/env python3
"""Validate separation between diagnosis and companion-health datasets."""

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.constants import VALID_LABELS


def _load_json(path: Path):
    if not path.exists():
        return None
    with path.open("r") as f:
        return json.load(f)


def validate_ground_truth(path: Path) -> list:
    errors = []
    payload = _load_json(path)
    if payload is None:
        errors.append(f"Missing ground truth file: {path}")
        return errors

    logs = payload.get("logs", [])
    for entry in logs:
        filename = entry.get("filename", "<unknown>")
        source_type = str(entry.get("source_type", "")).lower()
        if "companion" in source_type or "health" in source_type:
            errors.append(f"{filename}: companion-health entry found in diagnosis ground truth")

        labels = entry.get("labels", [])
        for label in labels:
            if label not in VALID_LABELS:
                errors.append(f"{filename}: unknown diagnosis label '{label}'")

    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate diagnosis/companion-health project boundaries")
    parser.add_argument("--ground-truth", default="ground_truth.json", help="Main diagnosis ground truth path")
    parser.add_argument(
        "--benchmark-ground-truth",
        default="data/clean_imports/flight_logs_dataset_2026-02-22/benchmark_ready/ground_truth.json",
        help="Benchmark-ready ground truth path",
    )
    args = parser.parse_args()

    all_errors = []
    all_errors.extend(validate_ground_truth(Path(args.ground_truth)))

    bench_path = Path(args.benchmark_ground_truth)
    if bench_path.exists():
        all_errors.extend(validate_ground_truth(bench_path))

    companion_root = Path("companion_health")
    if not companion_root.exists():
        all_errors.append("Missing companion_health root directory")

    if all_errors:
        print("Boundary validation failed:")
        for err in all_errors:
            print(f"- {err}")
        raise SystemExit(1)

    print("Boundary validation passed.")


if __name__ == "__main__":
    main()
