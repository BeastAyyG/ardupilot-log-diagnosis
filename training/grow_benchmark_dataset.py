#!/usr/bin/env python3
"""Collect and import a broader labeled batch for benchmark growth."""

import argparse
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.data.clean_import import run_clean_import
from src.data.forum_collector import collect_forum_logs


def _load_queries(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict) or not payload:
        raise ValueError(
            f"Query file must contain a non-empty label->query map: {path}"
        )
    return payload


def _label_counts(benchmark_gt: Path) -> Counter:
    with benchmark_gt.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    counts = Counter()
    for log in payload.get("logs", []):
        for label in log.get("labels", []):
            counts[label] += 1
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Grow benchmark dataset with expanded forum queries"
    )
    parser.add_argument(
        "--batch-name",
        default=f"forum_batch_expand_{date.today().isoformat()}",
        help="Batch folder suffix used under data/raw_downloads and data/clean_imports",
    )
    parser.add_argument(
        "--queries-json",
        default="docs/forum_queries.expanded.json",
        help="Path to JSON map of label->forum search query",
    )
    parser.add_argument(
        "--max-per-query",
        type=int,
        default=15,
        help="Maximum downloads per label query",
    )
    parser.add_argument(
        "--max-topics-per-query",
        type=int,
        default=80,
        help="Maximum forum topics scanned per query",
    )
    parser.add_argument(
        "--sleep-ms",
        type=int,
        default=100,
        help="Delay between requests in milliseconds",
    )
    parser.add_argument("--no-zip", action="store_true", help="Skip zip attachments")
    parser.add_argument(
        "--min-per-label",
        type=int,
        default=2,
        help="Warn when benchmark-ready labels have fewer than this many logs",
    )
    args = parser.parse_args()

    queries = _load_queries(Path(args.queries_json))

    raw_out = Path("data/raw_downloads") / args.batch_name
    clean_out = Path("data/clean_imports") / args.batch_name

    collect_summary = collect_forum_logs(
        output_root=str(raw_out),
        max_per_query=args.max_per_query,
        max_topics_per_query=args.max_topics_per_query,
        sleep_ms=args.sleep_ms,
        include_zip=not args.no_zip,
        query_overrides=queries,
    )

    import_summary = run_clean_import(
        source_root=str(raw_out),
        output_root=str(clean_out),
        copy_files=True,
    )

    benchmark_gt = clean_out / "benchmark_ready" / "ground_truth.json"
    counts = _label_counts(benchmark_gt) if benchmark_gt.exists() else Counter()

    print("Expanded batch complete")
    print(f"batch_name={args.batch_name}")
    print(f"raw_output={raw_out}")
    print(f"clean_output={clean_out}")
    print(f"downloaded={collect_summary.get('downloaded', 0)}")
    print(
        f"benchmark_trainable={import_summary.get('counts', {}).get('benchmark_trainable', 0)}"
    )
    print(f"benchmark_ground_truth={benchmark_gt}")
    print(f"label_distribution={dict(sorted(counts.items()))}")

    min_per_label = max(0, args.min_per_label)
    underrepresented = [
        label
        for label in sorted(queries.keys())
        if counts.get(label, 0) < min_per_label
    ]
    if underrepresented:
        print(f"underrepresented_labels(<{min_per_label})={underrepresented}")


if __name__ == "__main__":
    main()
