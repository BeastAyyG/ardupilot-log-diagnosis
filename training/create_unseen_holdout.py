#!/usr/bin/env python3
"""Create a SHA-deduped unseen holdout from clean-import batches.

The holdout contains only verified labeled logs whose SHA256 does not appear in
the excluded training batches.
"""

from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from pathlib import Path


def _load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _load_verified_manifest(batch: str) -> dict:
    path = Path(f"data/clean_imports/{batch}/manifests/clean_import_manifest.json")
    if not path.exists():
        raise FileNotFoundError(f"Missing manifest: {path}")

    rows = _load_json(path)
    return {
        row["file_name"]: row
        for row in rows
        if row.get("category") == "verified_labeled" and row.get("mapped_label")
    }


def _load_benchmark_logs(batch: str) -> list:
    path = Path(f"data/clean_imports/{batch}/benchmark_ready/ground_truth.json")
    if not path.exists():
        raise FileNotFoundError(f"Missing benchmark ground truth: {path}")
    payload = _load_json(path)
    return payload.get("logs", [])


def _dataset_path(batch: str) -> Path:
    return Path(f"data/clean_imports/{batch}/benchmark_ready/dataset")


def _copy_log(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create unseen holdout from candidate clean-import batches")
    parser.add_argument(
        "--exclude-batches",
        nargs="+",
        required=True,
        help="Batches used for training (their SHA256 hashes are excluded)",
    )
    parser.add_argument(
        "--candidate-batches",
        nargs="+",
        required=True,
        help="Batches to search for unseen holdout logs",
    )
    parser.add_argument(
        "--output-root",
        default="data/holdouts/unseen_holdout",
        help="Output directory for holdout dataset and metadata",
    )
    args = parser.parse_args()

    excluded_hashes = set()
    for batch in args.exclude_batches:
        manifest = _load_verified_manifest(batch)
        excluded_hashes.update(row["sha256"] for row in manifest.values())

    output_root = Path(args.output_root)
    dataset_out = output_root / "dataset"
    dataset_out.mkdir(parents=True, exist_ok=True)

    selected_logs = []
    selected_hashes = set()
    skipped_overlap = 0
    skipped_missing = 0

    for batch in args.candidate_batches:
        manifest = _load_verified_manifest(batch)
        logs = _load_benchmark_logs(batch)
        dataset_dir = _dataset_path(batch)

        for log in logs:
            filename = log.get("filename", "")
            row = manifest.get(filename)
            if row is None:
                skipped_missing += 1
                continue

            sha = row["sha256"]
            if sha in excluded_hashes or sha in selected_hashes:
                skipped_overlap += 1
                continue

            src_path = dataset_dir / filename
            if not src_path.exists():
                skipped_missing += 1
                continue

            out_name = f"{batch}__{filename}"
            _copy_log(src_path, dataset_out / out_name)

            selected_hashes.add(sha)
            selected_logs.append(
                {
                    "filename": out_name,
                    "labels": log.get("labels", []),
                    "source_url": row.get("source_url", ""),
                    "source_type": row.get("source_type", ""),
                    "resolved_download_url": row.get("resolved_download_url", ""),
                    "sha256": sha,
                    "origin_batch": batch,
                }
            )

    label_counter = Counter()
    batch_counter = Counter()
    for item in selected_logs:
        batch_counter[item["origin_batch"]] += 1
        for label in item["labels"]:
            label_counter[label] += 1

    gt_payload = {
        "metadata": {
            "description": "SHA-unseen holdout generated from clean-import batches",
            "exclude_batches": args.exclude_batches,
            "candidate_batches": args.candidate_batches,
            "total_logs": len(selected_logs),
            "label_distribution": dict(sorted(label_counter.items())),
            "origin_batch_distribution": dict(sorted(batch_counter.items())),
            "skipped_overlap": skipped_overlap,
            "skipped_missing": skipped_missing,
        },
        "logs": [
            {
                "filename": item["filename"],
                "labels": item["labels"],
                "source_url": item["source_url"],
                "source_type": item["source_type"],
                "confidence": "medium",
            }
            for item in selected_logs
        ],
    }

    output_root.mkdir(parents=True, exist_ok=True)
    gt_path = output_root / "ground_truth.json"
    gt_path.write_text(json.dumps(gt_payload, indent=2) + "\n", encoding="utf-8")

    manifest_path = output_root / "holdout_manifest.json"
    manifest_path.write_text(json.dumps(selected_logs, indent=2) + "\n", encoding="utf-8")

    report_lines = [
        "# Unseen Holdout Report",
        "",
        f"- Output root: `{output_root}`",
        f"- Exclude batches: `{', '.join(args.exclude_batches)}`",
        f"- Candidate batches: `{', '.join(args.candidate_batches)}`",
        f"- Selected unseen logs: **{len(selected_logs)}**",
        f"- Skipped due to overlap: **{skipped_overlap}**",
        f"- Skipped due to missing mapping/files: **{skipped_missing}**",
        "",
        "## Label Distribution",
        "",
        "| Label | Count |",
        "|---|---:|",
    ]
    for label, count in sorted(label_counter.items()):
        report_lines.append(f"| {label} | {count} |")

    report_lines.extend(
        [
            "",
            "## Origin Batch Distribution",
            "",
            "| Batch | Count |",
            "|---|---:|",
        ]
    )
    for batch, count in sorted(batch_counter.items()):
        report_lines.append(f"| {batch} | {count} |")

    report_lines.extend(
        [
            "",
            "## Artifacts",
            f"- `{gt_path}`",
            f"- `{manifest_path}`",
        ]
    )

    report_path = output_root / "report.md"
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    print("Unseen holdout created")
    print(f"output_root={output_root}")
    print(f"selected_logs={len(selected_logs)}")
    print(f"skipped_overlap={skipped_overlap}")
    print(f"skipped_missing={skipped_missing}")
    print(f"ground_truth={gt_path}")
    print(f"report={report_path}")


if __name__ == "__main__":
    main()
