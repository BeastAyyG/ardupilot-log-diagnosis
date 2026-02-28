#!/usr/bin/env python3
"""Mine expert-labeled logs from discuss.ardupilot.org."""

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.data.expert_label_miner import collect_expert_labeled_forum_logs


def main() -> None:
    parser = argparse.ArgumentParser(description="Mine expert-labeled forum logs")
    parser.add_argument(
        "--output-root",
        default="data/raw_downloads/forum_expert_batch",
        help="Output folder",
    )
    parser.add_argument("--queries-json", help="Path to JSON queries")
    parser.add_argument(
        "--after-date", help="Incremental search start date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--max-topics-per-query", type=int, default=120, help="Max topics per query"
    )
    parser.add_argument(
        "--max-downloads", type=int, default=300, help="Max downloaded payloads"
    )
    parser.add_argument(
        "--sleep-ms", type=int, default=300, help="Delay between requests (ms)"
    )
    parser.add_argument("--no-zip", action="store_true", help="Skip zip attachments")
    parser.add_argument("--state-path", help="Path to miner state JSON")
    parser.add_argument(
        "--existing-data-root",
        default="data",
        help="Data root for labeled-topic skipping",
    )
    parser.add_argument(
        "--no-skip-existing-labeled",
        action="store_true",
        help="Do not skip topics already present in existing ground truth files",
    )
    args = parser.parse_args()

    summary = collect_expert_labeled_forum_logs(
        output_root=args.output_root,
        queries_json=args.queries_json,
        max_topics_per_query=args.max_topics_per_query,
        max_downloads=args.max_downloads,
        sleep_ms=args.sleep_ms,
        include_zip=not args.no_zip,
        after_date=args.after_date,
        state_path=args.state_path,
        skip_existing_labeled_topics=not args.no_skip_existing_labeled,
        existing_data_root=args.existing_data_root,
    )

    print("Expert-labeled forum mining complete")
    print(f"output_root={summary['output_root']}")
    print(f"topics_scanned={summary['topics_scanned']}")
    print(f"topics_with_expert_label={summary['topics_with_expert_label']}")
    print(f"rows={summary['rows']}")
    print(f"downloaded={summary['downloaded']}")
    print(f"manifest_csv={summary['artifacts']['manifest_csv']}")
    print(f"block1_csv={summary['artifacts']['block1_csv']}")
    print(f"summary_json={summary['artifacts']['summary_json']}")


if __name__ == "__main__":
    main()
