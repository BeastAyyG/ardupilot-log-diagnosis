#!/usr/bin/env python3
"""Collect candidate logs from discuss.ardupilot.org."""

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.data.forum_collector import collect_forum_logs


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect candidate ArduPilot logs from forum search"
    )
    parser.add_argument(
        "--output-root",
        default="data/raw_downloads/forum_batch",
        help="Output folder for batch",
    )
    parser.add_argument(
        "--max-per-query", type=int, default=20, help="Max downloaded files per query"
    )
    parser.add_argument(
        "--max-topics-per-query",
        type=int,
        default=60,
        help="Max forum topics scanned per query",
    )
    parser.add_argument(
        "--sleep-ms", type=int, default=250, help="Request delay in milliseconds"
    )
    parser.add_argument("--no-zip", action="store_true", help="Skip zip attachments")
    parser.add_argument(
        "--queries-json", help="Path to JSON map of label->search query"
    )
    args = parser.parse_args()

    query_overrides = None
    if args.queries_json:
        with open(args.queries_json, "r") as f:
            query_overrides = json.load(f)

    summary = collect_forum_logs(
        output_root=args.output_root,
        max_per_query=args.max_per_query,
        max_topics_per_query=args.max_topics_per_query,
        sleep_ms=args.sleep_ms,
        include_zip=not args.no_zip,
        query_overrides=query_overrides,
    )

    print("Forum collection complete")
    print(f"output_root={summary['output_root']}")
    print(f"rows={summary['rows']}")
    print(f"downloaded={summary['downloaded']}")
    print(f"not_log_payload={summary['not_log_payload']}")
    print(f"download_failed={summary['download_failed']}")
    print(f"manifest_csv={summary['artifacts']['manifest_csv']}")


if __name__ == "__main__":
    main()
