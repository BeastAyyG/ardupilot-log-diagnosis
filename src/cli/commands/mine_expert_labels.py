from __future__ import annotations

from argparse import _SubParsersAction


def register(subparsers: _SubParsersAction) -> None:
    parser = subparsers.add_parser("mine-expert-labels", help="Mine discuss.ardupilot.org for logs with developer-diagnosed labels")
    parser.add_argument("--output-root", default="data/raw_downloads/forum_expert_batch", help="Output folder for downloaded files and expert manifests")
    parser.add_argument("--queries-json", help="Path to JSON queries (dict/list or {label, queries[]})")
    parser.add_argument("--after-date", help="Incremental search start date (YYYY-MM-DD)")
    parser.add_argument("--max-topics-per-query", type=int, default=120, help="Maximum topics scanned per query")
    parser.add_argument("--max-downloads", type=int, default=300, help="Maximum downloaded payloads")
    parser.add_argument("--sleep-ms", type=int, default=300, help="Delay between network requests in milliseconds")
    parser.add_argument("--no-zip", action="store_true", help="Skip zip attachments")
    parser.add_argument("--state-path", help="Path to miner state JSON for incremental runs")
    parser.add_argument("--existing-data-root", default="data", help="Data root used to skip topics already present in labeled datasets")
    parser.add_argument("--no-skip-existing-labeled", action="store_true", help="Do not skip topic URLs already present in ground_truth files")
    parser.add_argument("--enrich-only", action="store_true", help="Only enrich an existing crawler manifest with expert labels")
    parser.add_argument("--source-root", help="Source folder containing crawler_manifest.csv for --enrich-only mode")
    parser.add_argument("--input-manifest-name", default="crawler_manifest.csv", help="Input manifest filename for --enrich-only mode")
    parser.add_argument("--output-manifest-name", default="crawler_manifest_v2.csv", help="Output manifest filename for --enrich-only mode")
    parser.add_argument("--output-block1-name", default="block1_ardupilot_discuss.csv", help="Output block1 CSV filename for --enrich-only mode")
    parser.set_defaults(func=run)


def run(args) -> None:
    from src.data.expert_label_miner import (
        collect_expert_labeled_forum_logs,
        enrich_manifest_with_expert_labels,
    )

    if args.enrich_only:
        if not args.source_root:
            raise ValueError("--source-root is required when --enrich-only is used")

        summary = enrich_manifest_with_expert_labels(
            source_root=args.source_root,
            input_manifest_name=args.input_manifest_name,
            output_manifest_name=args.output_manifest_name,
            output_block1_name=args.output_block1_name,
            sleep_ms=args.sleep_ms,
        )
        print("Expert manifest enrichment complete.")
        print(f"Source root: {summary.get('source_root')}")
        print(f"Input manifest: {summary.get('input_manifest')}")
        print(f"Output manifest: {summary.get('output_manifest')}")
        print(f"block1 CSV: {summary.get('output_block1')}")
        print(f"Rows: {summary.get('rows', 0)}")
        print(f"Topics scanned: {summary.get('topics_scanned', 0)}")
        print(f"Topics with expert label: {summary.get('topics_with_expert_label', 0)}")
        print(f"Rows with label: {summary.get('rows_with_label', 0)}")
        print(f"Summary JSON: {summary.get('summary_json')}")
        return

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

    artifacts = summary.get("artifacts", {})
    print("Expert-labeled forum mining complete.")
    print(f"Output root: {summary.get('output_root')}")
    print(f"Topics scanned: {summary.get('topics_scanned', 0)}")
    print(f"Topics with expert label: {summary.get('topics_with_expert_label', 0)}")
    print(f"Rows: {summary.get('rows', 0)}")
    print(f"Downloaded: {summary.get('downloaded', 0)}")
    print(f"Not-log payload: {summary.get('not_log_payload', 0)}")
    print(f"Download failed: {summary.get('download_failed', 0)}")
    print(f"Manifest CSV: {artifacts.get('manifest_csv')}")
    print(f"block1 CSV: {artifacts.get('block1_csv')}")
    print(f"Summary JSON: {artifacts.get('summary_json')}")
    print(f"State JSON: {artifacts.get('state_json')}")
