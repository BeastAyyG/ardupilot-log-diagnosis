#!/usr/bin/env python3
"""Compatibility wrapper for forum data collection.

Deprecated script path retained for convenience. It now uses the new
production-safe collector and does not modify `ground_truth.json`.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.data.forum_collector import collect_forum_logs


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect forum logs (deprecated entrypoint)")
    parser.add_argument("--output-root", default="data/raw_downloads/forum_batch", help="Output directory")
    parser.add_argument("--max-per-query", type=int, default=20, help="Max downloads per query")
    parser.add_argument("--max-topics-per-query", type=int, default=60, help="Max topics to scan per query")
    parser.add_argument("--sleep-ms", type=int, default=250, help="Delay between requests")
    parser.add_argument("--no-zip", action="store_true", help="Skip zip attachments")
    parser.add_argument("--queries-json", help="Path to JSON map of label->search query")
    args = parser.parse_args()

    query_overrides = None
    if args.queries_json:
        with open(args.queries_json, "r") as f:
            query_overrides = json.load(f)

    print("Note: `download_from_forum.py` is deprecated. Prefer `python -m src.cli.main collect-forum`.")
    summary = collect_forum_logs(
        output_root=args.output_root,
        max_per_query=args.max_per_query,
        max_topics_per_query=args.max_topics_per_query,
        sleep_ms=args.sleep_ms,
        include_zip=not args.no_zip,
        query_overrides=query_overrides,
    )

    print(f"Downloaded={summary['downloaded']} rows={summary['rows']}")
    print(f"Manifest={summary['artifacts']['manifest_csv']}")


if __name__ == "__main__":
    main()
