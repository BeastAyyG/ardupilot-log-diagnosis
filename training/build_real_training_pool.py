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


def _index_backup_files(backup_roots: List[Path]) -> Dict[str, List[Path]]:
    """Index BIN files by both stored name and de-prefixed original name."""
    index: Dict[str, List[Path]] = {}
    for backup_root in backup_roots:
        if not backup_root.exists():
            print(f"Warning: backup root does not exist: {backup_root}")
            continue
        for path in backup_root.rglob("*"):
            if not path.is_file() or path.suffix.lower() != ".bin":
                continue
            names = {path.name.casefold()}
            if "__" in path.name:
                names.add(path.name.split("__", 1)[1].casefold())
            for name in names:
                index.setdefault(name, []).append(path)
    return index


def _resolve_source_file(
    file_name: str,
    direct_candidates: List[Path],
    backup_index: Dict[str, List[Path]],
    expected_sha256: str = "",
) -> Path | None:
    candidates = [path for path in direct_candidates if path.is_file()]
    candidates.extend(backup_index.get(file_name.casefold(), []))

    unique_candidates = []
    seen = set()
    for path in candidates:
        resolved = str(path.resolve()).casefold()
        if resolved not in seen:
            unique_candidates.append(path)
            seen.add(resolved)

    if expected_sha256:
        expected = expected_sha256.casefold()
        for path in unique_candidates:
            if _sha256(path).casefold() == expected:
                return path
        return None

    return unique_candidates[0] if unique_candidates else None


def _collect_verified_candidates(
    clean_import_root: Path,
    exclude_batches: set[str],
    backup_index: Dict[str, List[Path]] | None = None,
    stats: dict | None = None,
) -> List[dict]:
    backup_index = backup_index or {}
    stats = stats if stats is not None else {}
    stats.setdefault("verified_rows", 0)
    stats.setdefault("missing_verified_files", 0)

    candidates: List[dict] = []
    for manifest in sorted(
        clean_import_root.glob("*/manifests/clean_import_manifest.json")
    ):
        batch = manifest.parent.parent.name
        if batch in exclude_batches:
            continue
        rows = _load_json(manifest)
        for row in rows:
            if row.get("category") != "verified_labeled":
                continue
            stats["verified_rows"] += 1
            label = row.get("mapped_label", "")
            if label not in VALID_LABELS:
                continue

            file_name = row.get("file_name", "")
            sha = row.get("sha256", "")
            batch_root = clean_import_root / batch
            src_file = _resolve_source_file(
                file_name,
                [
                    batch_root / "benchmark_ready" / "dataset" / file_name,
                    batch_root / "logs" / "verified_labeled" / file_name,
                    batch_root / row.get("source_path", ""),
                ],
                backup_index,
                expected_sha256=sha,
            )
            if src_file is None:
                stats["missing_verified_files"] += 1
                continue

            sha = sha or _sha256(src_file)
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


def _collect_manual_candidates(
    manual_gt_path: Path,
    backup_index: Dict[str, List[Path]] | None = None,
    stats: dict | None = None,
) -> List[dict]:
    backup_index = backup_index or {}
    stats = stats if stats is not None else {}
    stats.setdefault("manual_labeled_rows", 0)
    stats.setdefault("missing_manual_files", 0)

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
        stats["manual_labeled_rows"] += 1
        if label not in VALID_LABELS:
            continue

        src_file = _resolve_source_file(
            file_name,
            [base_dir / file_name, *base_dir.glob(f"*/{file_name}")],
            backup_index,
        )
        if src_file is None:
            stats["missing_manual_files"] += 1
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
                "source_type": (payload.get("source") or "manual_review").strip()
                or "manual_review",
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
                "sha256": sha,
                "origin_batch": item["batch"],
                "human_verified": True,
                "trainable": True,
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
        "--backup-root",
        action="append",
        default=[],
        help=(
            "Optional raw-backup root to recover BIN files omitted from Git. "
            "May be supplied more than once."
        ),
    )
    parser.add_argument(
        "--exclude-batches",
        nargs="*",
        default=[],
        help="Optional clean-import batch names to exclude (useful to preserve unseen holdouts)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve and validate inputs without replacing the output dataset.",
    )
    args = parser.parse_args()

    clean_import_root = Path(args.clean_import_root)
    manual_gt_path = Path(args.manual_ground_truth)
    output_root = Path(args.output_root)

    exclude_batches = set(args.exclude_batches)
    backup_roots = [Path(path) for path in args.backup_root]
    backup_index = _index_backup_files(backup_roots)
    collection_stats: dict = {}
    verified = _collect_verified_candidates(
        clean_import_root,
        exclude_batches,
        backup_index=backup_index,
        stats=collection_stats,
    )
    manual = _collect_manual_candidates(
        manual_gt_path,
        backup_index=backup_index,
        stats=collection_stats,
    )

    selected = []
    seen_sha: Dict[str, str] = {}
    skipped_verified_dupes = 0
    skipped_manual_dupes = 0
    conflicting_labels = 0

    # deterministic: verified first, then manual (manual only adds new SHA)
    for item in verified:
        sha = item["sha256"]
        if sha in seen_sha:
            skipped_verified_dupes += 1
            if seen_sha[sha] != item["label"]:
                conflicting_labels += 1
            continue
        seen_sha[sha] = item["label"]
        selected.append(item)

    for item in manual:
        sha = item["sha256"]
        if sha in seen_sha:
            skipped_manual_dupes += 1
            if seen_sha[sha] != item["label"]:
                conflicting_labels += 1
            continue
        seen_sha[sha] = item["label"]
        selected.append(item)

    if not selected:
        raise SystemExit(
            "No verified training logs could be resolved; refusing to replace "
            f"the existing dataset at {output_root}. Supply --backup-root if "
            "the BIN files are stored outside the repository."
        )

    print(
        f"Resolved {len(selected)} unique verified logs "
        f"({collection_stats.get('missing_verified_files', 0)} verified and "
        f"{collection_stats.get('missing_manual_files', 0)} manual files missing)."
    )
    if args.dry_run:
        print("Dry run complete; output dataset was not changed.")
        return

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
            # Record source identities without leaking machine-specific paths.
            "backup_roots": [path.name for path in backup_roots],
            "conflicting_labels": conflicting_labels,
            **collection_stats,
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
    print(f"conflicting_labels={summary['conflicting_labels']}")
    print(f"missing_verified_files={summary['missing_verified_files']}")
    print(f"missing_manual_files={summary['missing_manual_files']}")
    print(f"ground_truth={summary['ground_truth_path']}")
    print(f"build_summary={summary_path}")


if __name__ == "__main__":
    main()
