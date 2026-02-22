"""Build training dataset from labeled .BIN logs."""

import argparse
import csv
import json
import os
import sys
from collections import Counter
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.constants import FEATURE_NAMES, VALID_LABELS
from src.features.pipeline import FeaturePipeline
from src.parser.bin_parser import LogParser

CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}


def _confidence_ok(log_confidence: str, min_confidence: str) -> bool:
    log_level = CONFIDENCE_ORDER.get(str(log_confidence).strip().lower(), CONFIDENCE_ORDER["medium"])
    min_level = CONFIDENCE_ORDER[min_confidence]
    return log_level >= min_level


def build(
    ground_truth_path: str = "ground_truth.json",
    dataset_dir: str = "dataset",
    output_features: str = "training/features.csv",
    output_labels: str = "training/labels.csv",
    report_path: str = "training/dataset_build_report.json",
    min_confidence: str = "low",
    trainable_only: bool = True,
) -> dict:
    if not os.path.exists(ground_truth_path):
        print(f"File not found: {ground_truth_path}")
        return {}

    with open(ground_truth_path, "r") as f:
        data = json.load(f)

    logs = data.get("logs", [])
    if not logs:
        print("No logs found in ground truth.")
        return {}

    pipeline = FeaturePipeline()
    feature_rows = []
    label_rows = []

    skipped_missing_file = 0
    skipped_low_confidence = 0
    skipped_not_trainable = 0
    failed_extraction = 0
    processed = 0

    label_counter = Counter()
    source_type_counter = Counter()

    for log_entry in logs:
        filename = log_entry.get("filename")
        labels = log_entry.get("labels", [])
        confidence = log_entry.get("confidence", "medium")
        source_type = log_entry.get("source_type", "unknown")
        trainable = bool(log_entry.get("trainable", True))

        if trainable_only and not trainable:
            skipped_not_trainable += 1
            continue

        if not _confidence_ok(confidence, min_confidence):
            skipped_low_confidence += 1
            continue

        filepath = os.path.join(dataset_dir, filename)
        if not os.path.exists(filepath):
            print(f"Skipping {filename}: File not found in {dataset_dir}")
            skipped_missing_file += 1
            continue

        parser = LogParser(filepath)
        parsed = parser.parse()
        if not parsed.get("messages"):
            print(f"Skipping {filename}: Failed to parse or empty.")
            failed_extraction += 1
            continue

        features = pipeline.extract(parsed)

        feat_row = [features.get(name, 0.0) for name in FEATURE_NAMES]
        label_row = [1 if label in labels else 0 for label in VALID_LABELS]

        feature_rows.append(feat_row)
        label_rows.append(label_row)
        processed += 1

        for label in labels:
            label_counter[label] += 1
        source_type_counter[source_type] += 1

    features_parent = os.path.dirname(output_features)
    labels_parent = os.path.dirname(output_labels)
    report_parent = os.path.dirname(report_path)

    if features_parent:
        os.makedirs(features_parent, exist_ok=True)
    if labels_parent:
        os.makedirs(labels_parent, exist_ok=True)
    if report_parent:
        os.makedirs(report_parent, exist_ok=True)

    with open(output_features, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(FEATURE_NAMES)
        writer.writerows(feature_rows)

    with open(output_labels, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(VALID_LABELS)
        writer.writerows(label_rows)

    report = {
        "ground_truth_path": ground_truth_path,
        "dataset_dir": dataset_dir,
        "total_entries": len(logs),
        "processed": processed,
        "failed_extraction": failed_extraction,
        "skipped_missing_file": skipped_missing_file,
        "skipped_low_confidence": skipped_low_confidence,
        "skipped_not_trainable": skipped_not_trainable,
        "min_confidence": min_confidence,
        "trainable_only": trainable_only,
        "label_distribution": dict(sorted(label_counter.items())),
        "source_type_distribution": dict(sorted(source_type_counter.items())),
        "output_features": output_features,
        "output_labels": output_labels,
    }

    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    print("Dataset built successfully.")
    print(f"Processed logs: {processed}")
    print(f"Failed extractions: {failed_extraction}")
    print(f"Skipped (missing file): {skipped_missing_file}")
    print(f"Skipped (confidence): {skipped_low_confidence}")
    print(f"Skipped (not trainable): {skipped_not_trainable}")
    print(f"Features saved to: {output_features}")
    print(f"Labels saved to: {output_labels}")
    print(f"Build report saved to: {report_path}")

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build training dataset from labeled BIN logs")
    parser.add_argument("--ground-truth", default="ground_truth.json", help="Path to ground_truth.json")
    parser.add_argument("--dataset-dir", default="dataset", help="Directory containing BIN logs")
    parser.add_argument("--features-out", default="training/features.csv", help="Output CSV for features")
    parser.add_argument("--labels-out", default="training/labels.csv", help="Output CSV for labels")
    parser.add_argument(
        "--report-out",
        default="training/dataset_build_report.json",
        help="Output JSON report path",
    )
    parser.add_argument(
        "--min-confidence",
        choices=["low", "medium", "high"],
        default="low",
        help="Minimum label confidence to include",
    )
    parser.add_argument(
        "--include-non-trainable",
        action="store_true",
        help="Include entries marked trainable=false",
    )

    args = parser.parse_args()
    build(
        ground_truth_path=args.ground_truth,
        dataset_dir=args.dataset_dir,
        output_features=args.features_out,
        output_labels=args.labels_out,
        report_path=args.report_out,
        min_confidence=args.min_confidence,
        trainable_only=not args.include_non_trainable,
    )


if __name__ == "__main__":
    main()
