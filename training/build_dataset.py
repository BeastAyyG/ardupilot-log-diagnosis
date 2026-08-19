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
from .data_contract import canonical_source_group, finite_sha256
from .window_slicer import slice_log_into_windows

CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}


def _confidence_ok(log_confidence: str, min_confidence: str) -> bool:
    log_level = CONFIDENCE_ORDER.get(
        str(log_confidence).strip().lower(), CONFIDENCE_ORDER["medium"]
    )
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
    output_groups: str = "training/groups.csv",
    window_sec: float = 5.0,
    overlap: float = 0.5,
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
    group_rows = []
    seen_sha256 = set()

    # Resolve source groups before extraction so a URL that contains multiple
    # contradictory labels cannot silently become a one-label incident. Such
    # rows need an explicit incident_id/source_group in ground truth first.
    source_group_labels = {}
    source_group_entries = {}
    for entry in logs:
        filename = str(entry.get("filename", "") or "")
        labels_for_entry = [
            str(label).strip()
            for label in entry.get("labels", [])
            if str(label).strip() in VALID_LABELS
        ]
        if not labels_for_entry:
            continue
        source_group = canonical_source_group(entry, filename)
        source_group_labels.setdefault(source_group, set()).add(labels_for_entry[0])
        source_group_entries.setdefault(source_group, []).append(filename)
    ambiguous_source_groups = {
        group: sorted(labels)
        for group, labels in source_group_labels.items()
        if len(labels) > 1
    }

    skipped_missing_file = 0
    skipped_low_confidence = 0
    skipped_not_trainable = 0
    skipped_duplicate_sha256 = 0
    skipped_ambiguous_group = 0
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

        source_group = canonical_source_group(log_entry, filename)
        if source_group in ambiguous_source_groups:
            skipped_ambiguous_group += 1
            continue

        filepath = os.path.join(dataset_dir, filename)
        if not os.path.exists(filepath):
            print(f"Skipping {filename}: File not found in {dataset_dir}")
            skipped_missing_file += 1
            continue

        # A source manifest can contain the same payload under different
        # attachment names.  Never count the duplicate as an independent
        # flight; this also prevents the same bytes from crossing the split.
        try:
            sha256 = finite_sha256(filepath)
        except OSError:
            failed_extraction += 1
            continue
        if sha256 in seen_sha256:
            skipped_duplicate_sha256 += 1
            continue
        seen_sha256.add(sha256)

        # Preserve the explicit label order from ground truth.  The previous
        # implementation reconstructed a primary label from VALID_LABELS
        # column order, which silently changed e.g. [ekf_failure,
        # compass_interference] into compass_interference.
        active_labels = [
            str(label).strip()
            for label in labels
            if str(label).strip() in VALID_LABELS
        ]
        primary_label = active_labels[0] if active_labels else ""
        source_url = str(log_entry.get("source_url", "") or "").strip()

        parser = LogParser(filepath)
        parsed = parser.parse()
        if not parsed.get("messages"):
            print(f"Skipping {filename}: Failed to parse or empty.")
            failed_extraction += 1
            continue

        # For non-healthy logs with short duration, or for standard extraction, just use the whole log.
        # But if slicing is requested (implied by blueprint), we slice it.
        # We will extract features from the full log AND the slices to massively augment the dataset.
        slices = slice_log_into_windows(parsed, window_sec=window_sec, overlap=overlap)

        # Add the full log as well, but do not duplicate short logs where the
        # slicer already returned the original object as its only slice.
        if all(log_slice is not parsed for log_slice in slices):
            slices.append(parsed)

        for log_slice in slices:
            features = pipeline.extract(log_slice)

            feat_row = [features.get(name, 0.0) for name in FEATURE_NAMES]
            label_row = [1 if label in labels else 0 for label in VALID_LABELS]

            feature_rows.append(feat_row)
            label_rows.append(label_row)
            group_rows.append([filename, source_group, source_url, primary_label, sha256])
            processed += 1

        for label in labels:
            label_counter[label] += 1
        source_type_counter[source_type] += 1

    features_parent = os.path.dirname(output_features)
    labels_parent = os.path.dirname(output_labels)
    groups_parent = os.path.dirname(output_groups)
    report_parent = os.path.dirname(report_path)

    if features_parent:
        os.makedirs(features_parent, exist_ok=True)
    if labels_parent:
        os.makedirs(labels_parent, exist_ok=True)
    if groups_parent:
        os.makedirs(groups_parent, exist_ok=True)
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

    with open(output_groups, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["source_log", "source_group", "source_url", "primary_label", "sha256"]
        )
        writer.writerows(group_rows)

    report = {
        "ground_truth_path": ground_truth_path,
        "dataset_dir": dataset_dir,
        "window_sec": window_sec,
        "overlap": overlap,
        "total_entries": len(logs),
        "processed": processed,
        "failed_extraction": failed_extraction,
        "skipped_missing_file": skipped_missing_file,
        "skipped_low_confidence": skipped_low_confidence,
        "skipped_not_trainable": skipped_not_trainable,
        "skipped_duplicate_sha256": skipped_duplicate_sha256,
        "skipped_ambiguous_group": skipped_ambiguous_group,
        "ambiguous_source_groups": ambiguous_source_groups,
        "ambiguous_source_group_files": {
            group: sorted(source_group_entries[group])
            for group in ambiguous_source_groups
        },
        "unique_source_logs": len(seen_sha256),
        "unique_source_groups": len({row[1] for row in group_rows}),
        "source_group_policy": "explicit incident/source_url, otherwise filename",
        "min_confidence": min_confidence,
        "trainable_only": trainable_only,
        "label_distribution": dict(sorted(label_counter.items())),
        "source_type_distribution": dict(sorted(source_type_counter.items())),
        "output_features": output_features,
        "output_labels": output_labels,
        "output_groups": output_groups,
    }

    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    print("Dataset built successfully.")
    print(f"Processed logs: {processed}")
    print(f"Failed extractions: {failed_extraction}")
    print(f"Skipped (missing file): {skipped_missing_file}")
    print(f"Skipped (confidence): {skipped_low_confidence}")
    print(f"Skipped (not trainable): {skipped_not_trainable}")
    print(f"Skipped (duplicate SHA256): {skipped_duplicate_sha256}")
    print(f"Skipped (ambiguous source groups): {skipped_ambiguous_group}")
    print(f"Features saved to: {output_features}")
    print(f"Labels saved to: {output_labels}")
    print(f"Groups saved to: {output_groups}")
    print(f"Build report saved to: {report_path}")

    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build training dataset from labeled BIN logs"
    )
    parser.add_argument(
        "--ground-truth", default="ground_truth.json", help="Path to ground_truth.json"
    )
    parser.add_argument(
        "--dataset-dir", default="dataset", help="Directory containing BIN logs"
    )
    parser.add_argument(
        "--features-out",
        default="training/features.csv",
        help="Output CSV for features",
    )
    parser.add_argument(
        "--labels-out", default="training/labels.csv", help="Output CSV for labels"
    )
    parser.add_argument(
        "--groups-out",
        default="training/groups.csv",
        help="Output CSV identifying the source log for each row",
    )
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
    parser.add_argument(
        "--window-sec",
        type=float,
        default=5.0,
        help="Window size for augmentation; use 30-60 seconds for faster, less-correlated training rows",
    )
    parser.add_argument(
        "--overlap",
        type=float,
        default=0.5,
        help="Fractional overlap between augmented windows",
    )

    args = parser.parse_args()
    build(
        ground_truth_path=args.ground_truth,
        dataset_dir=args.dataset_dir,
        output_features=args.features_out,
        output_labels=args.labels_out,
        output_groups=args.groups_out,
        report_path=args.report_out,
        min_confidence=args.min_confidence,
        trainable_only=not args.include_non_trainable,
        window_sec=args.window_sec,
        overlap=args.overlap,
    )


if __name__ == "__main__":
    main()
