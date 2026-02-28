#!/usr/bin/env python3
"""Refresh metadata block in ground_truth.json from current log entries."""

import argparse
import json
from collections import Counter
from datetime import date
from pathlib import Path


def refresh(path: Path) -> dict:
    with path.open("r") as f:
        data = json.load(f)

    logs = data.get("logs", [])
    label_counter = Counter()
    for entry in logs:
        for label in entry.get("labels", []):
            label_counter[label] += 1

    metadata = data.get("metadata", {})
    metadata["last_updated"] = date.today().isoformat()
    metadata["total_logs"] = len(logs)
    metadata["label_distribution"] = dict(sorted(label_counter.items()))
    data["metadata"] = metadata

    with path.open("w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")

    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Refresh metadata in ground_truth.json"
    )
    parser.add_argument(
        "--path", default="ground_truth.json", help="Path to ground_truth.json"
    )
    args = parser.parse_args()

    metadata = refresh(Path(args.path))
    print("Updated ground truth metadata.")
    print(f"total_logs={metadata.get('total_logs')}")
    print(f"last_updated={metadata.get('last_updated')}")
    print(f"label_distribution={metadata.get('label_distribution')}")


if __name__ == "__main__":
    main()
