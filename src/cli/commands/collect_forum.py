from __future__ import annotations

import json
from argparse import _SubParsersAction


def register(subparsers: _SubParsersAction) -> None:
    parser = subparsers.add_parser("collect-forum", help="Collect candidate logs from discuss.ardupilot.org")
    parser.add_argument("--output-root", default="data/raw_downloads/forum_batch", help="Output folder for downloaded files and manifest")
    parser.add_argument("--max-per-query", type=int, default=20, help="Maximum downloads per label query")
    parser.add_argument("--max-topics-per-query", type=int, default=60, help="Maximum forum topics scanned per query")
    parser.add_argument("--sleep-ms", type=int, default=250, help="Delay between download requests in milliseconds")
    parser.add_argument("--no-zip", action="store_true", help="Skip zip attachments")
    parser.add_argument("--queries-json", help="Path to JSON map of label->search query")
    parser.set_defaults(func=run)


def run(args) -> None:
    from src.data.forum_collector import collect_forum_logs

    query_overrides = None
    if args.queries_json:
        with open(args.queries_json, "r") as file_obj:
            query_overrides = json.load(file_obj)

    summary = collect_forum_logs(
        output_root=args.output_root,
        max_per_query=args.max_per_query,
        max_topics_per_query=args.max_topics_per_query,
        sleep_ms=args.sleep_ms,
        include_zip=not args.no_zip,
        query_overrides=query_overrides,
    )

    artifacts = summary.get("artifacts", {})
    print("Forum collection complete.")
    print(f"Output root: {summary.get('output_root')}")
    print(f"Rows: {summary.get('rows', 0)}")
    print(f"Downloaded: {summary.get('downloaded', 0)}")
    print(f"Not-log payload: {summary.get('not_log_payload', 0)}")
    print(f"Download failed: {summary.get('download_failed', 0)}")
    print(f"Manifest CSV: {artifacts.get('manifest_csv')}")
    print(f"Summary JSON: {artifacts.get('summary_json')}")
