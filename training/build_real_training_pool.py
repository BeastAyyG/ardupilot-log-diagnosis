#!/usr/bin/env python3
"""Build a real-only training pool from verified labels and manual review.

This script intentionally excludes fabricated labels. It assembles a deduped
dataset using:
1) verified_labeled logs from clean-import manifests
2) optional manually reviewed labels from a to_label ground_truth.json
"""

from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import sys


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.constants import VALID_LABELS


def _load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _sha256(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _safe_confidence(value: str) -> str:
    v = (value or "").strip().lower()
    return v if v in {"medium", "high"} else "medium"


def _normalize_url(value: str) -> str:
    v = (value or "").strip()
    if not v or v.upper() == "N/A":
        return ""
    return v


def _collect_verified_candidates(clean_import_root: Path, exclude_batches: set[str]) -> List[dict]:
    candidates: List[dict] = []
    for manifest in sorted(clean_import_root.glob("*/manifests/clean_import_manifest.json")):
        batch = manifest.parent.parent.name
        if batch in exclude_batches:
            continue
        rows = _load_json(manifest)
        for row in rows:
            if row.get("category") != "verified_labeled":
                continue
            label = row.get("mapped_label", "")
            if label not in VALID_LABELS:
                continue

            src_file = clean_import_root / batch / "logs" / "verified_labeled" / row.get("file_name", "")
            if not src_file.exists():
                continue

            sha = row.get("sha256", "") or _sha256(src_file)
            candidates.append(
                {
                    "source": "verified_labeled",
                    "batch": batch,
                    "src_file": src_file,
                    "sha256": sha,
                    "label": label,
                    "confidence": "medium",
                    "source_url": _normalize_url(row.get("source_url", "")),
                    "source_type": row.get("source_type", "unknown") or "unknown",
                    "expert_quote": row.get("expert_quote", ""),
                }
            )
    return candidates


def _collect_manual_candidates(manual_gt_path: Path) -> List[dict]:
    if not manual_gt_path.exists():
        return []

    raw = _load_json(manual_gt_path)
    if not isinstance(raw, dict):
        return []

    base_dir = manual_gt_path.parent
    candidates: List[dict] = []
    for file_name, payload in raw.items():
        if not isinstance(payload, dict):
            continue
        label = (payload.get("label") or "").strip()
        if not label:
            continue
        if label not in VALID_LABELS:
            continue

        src_file = base_dir / file_name
        if not src_file.exists():
            continue

        sha = _sha256(src_file)
        candidates.append(
            {
                "source": "manual_review",
                "batch": base_dir.name,
                "src_file": src_file,
                "sha256": sha,
                "label": label,
                "confidence": _safe_confidence(payload.get("confidence", "medium")),
                "source_url": _normalize_url(payload.get("url", "")),
                "source_type": (payload.get("source") or "manual_review").strip() or "manual_review",
                "expert_quote": (payload.get("reason") or "").strip(),
            }
        )
    return candidates


def _write_output(output_root: Path, selected: List[dict]) -> dict:
    dataset_dir = output_root / "dataset"
    dataset_dir.mkdir(parents=True, exist_ok=True)

    logs = []
    label_counter = Counter()
    source_counter = Counter()

    for item in selected:
        sha = item["sha256"]
        src_file: Path = item["src_file"]
        out_name = f"{sha[:10]}__{src_file.name}"
        shutil.copy2(src_file, dataset_dir / out_name)

        logs.append(
            {
                "filename": out_name,
                "labels": [item["label"]],
                "source_url": item["source_url"],
                "source_type": item["source_type"],
                "expert_quote": item["expert_quote"],
                "confidence": item["confidence"],
            }
        )
        label_counter[item["label"]] += 1
        source_counter[item["source"]] += 1

    gt = {
        "metadata": {
            "description": "Real-only training pool (verified + manual review)",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "total_logs": len(logs),
            "label_distribution": dict(sorted(label_counter.items())),
            "source_distribution": dict(sorted(source_counter.items())),
            "policy": {
                "fabricated_labels": False,
                "sha_deduped": True,
            },
        },
        "logs": logs,
    }

    gt_path = output_root / "ground_truth.json"
    gt_path.write_text(json.dumps(gt, indent=2) + "\n", encoding="utf-8")

    return {
        "ground_truth_path": str(gt_path),
        "dataset_dir": str(dataset_dir),
        "total_logs": len(logs),
        "label_distribution": dict(sorted(label_counter.items())),
        "source_distribution": dict(sorted(source_counter.items())),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build real-only training pool")
    parser.add_argument(
        "--clean-import-root",
        default="data/clean_imports",
        help="Root containing clean-import batches",
    )
    parser.add_argument(
        "--manual-ground-truth",
        default="data/to_label/2026-02-23_batch/ground_truth.json",
        help="Path to manually reviewed labeling JSON",
    )
    parser.add_argument(
        "--output-root",
        default="data/final_training_dataset_2026-02-23",
        help="Output folder containing dataset/ and ground_truth.json",
    )
    parser.add_argument(
        "--exclude-batches",
        nargs="*",
        default=[],
        help="Optional clean-import batch names to exclude (useful to preserve unseen holdouts)",
    )
    args = parser.parse_args()

    clean_import_root = Path(args.clean_import_root)
    manual_gt_path = Path(args.manual_ground_truth)
    output_root = Path(args.output_root)

    exclude_batches = set(args.exclude_batches)
    verified = _collect_verified_candidates(clean_import_root, exclude_batches)
    manual = _collect_manual_candidates(manual_gt_path)

    selected = []
    seen_sha: Dict[str, str] = {}
    skipped_verified_dupes = 0
    skipped_manual_dupes = 0

    # deterministic: verified first, then manual (manual only adds new SHA)
    for item in verified:
        sha = item["sha256"]
        if sha in seen_sha:
            skipped_verified_dupes += 1
            continue
        seen_sha[sha] = item["label"]
        selected.append(item)

    for item in manual:
        sha = item["sha256"]
        if sha in seen_sha:
            skipped_manual_dupes += 1
            continue
        seen_sha[sha] = item["label"]
        selected.append(item)

    if output_root.exists():
        shutil.rmtree(output_root)

    summary = _write_output(output_root, selected)
    summary.update(
        {
            "verified_candidates": len(verified),
            "manual_candidates": len(manual),
            "skipped_verified_dupes": skipped_verified_dupes,
            "skipped_manual_dupes": skipped_manual_dupes,
            "manual_labeled_count": len(manual),
            "excluded_batches": sorted(exclude_batches),
        }
    )

    summary_path = output_root / "build_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print("Built real-only training dataset")
    print(f"output_root={output_root}")
    print(f"total_logs={summary['total_logs']}")
    print(f"label_distribution={summary['label_distribution']}")
    print(f"source_distribution={summary['source_distribution']}")
    print(f"verified_candidates={summary['verified_candidates']}")
    print(f"manual_candidates={summary['manual_candidates']}")
    print(f"skipped_verified_dupes={summary['skipped_verified_dupes']}")
    print(f"skipped_manual_dupes={summary['skipped_manual_dupes']}")
    print(f"ground_truth={summary['ground_truth_path']}")
    print(f"build_summary={summary_path}")


if __name__ == "__main__":
    main()
