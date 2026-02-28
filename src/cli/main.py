import argparse
import os
import json
from pathlib import Path
from src.parser.bin_parser import LogParser
from src.features.pipeline import FeaturePipeline
from src.diagnosis.hybrid_engine import HybridEngine
from src.diagnosis.rule_engine import RuleEngine
from src.diagnosis.decision_policy import evaluate_decision
from .formatter import DiagnosisFormatter


def _find_latest_clean_benchmark():
    root = Path("data/clean_imports")
    if not root.exists():
        return None, None

    candidates = sorted(
        root.glob("*/benchmark_ready/ground_truth.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return None, None

    gt_path = candidates[0]
    dataset_dir = gt_path.parent / "dataset"
    if not dataset_dir.exists():
        return None, None

    return str(dataset_dir), str(gt_path)


def cmd_analyze(args):
    parser = LogParser(args.logfile)
    parsed = parser.parse()

    pipeline = FeaturePipeline()
    features = pipeline.extract(parsed)

    if args.no_ml:
        engine = RuleEngine()
    else:
        engine = HybridEngine()

    diagnoses = engine.diagnose(features)
    decision = evaluate_decision(diagnoses)

    formatter = DiagnosisFormatter()
    metadata = features.get("_metadata", {})

    if args.json:
        output = formatter.format_json(diagnoses, metadata, features, decision=decision)
    else:
        output = formatter.format_terminal(diagnoses, metadata, decision=decision)

    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
        print(f"Report saved to {args.output}")
    else:
        print(output)


def cmd_features(args):
    parser = LogParser(args.logfile)
    parsed = parser.parse()

    pipeline = FeaturePipeline()
    features = pipeline.extract(parsed)

    print(json.dumps(features, indent=2))


def cmd_benchmark(args):
    from src.benchmark.suite import BenchmarkSuite
    from src.benchmark.reporter import BenchmarkReporter

    dataset_dir = args.dataset_dir
    ground_truth = args.ground_truth

    default_args_used = (
        args.dataset_dir == "dataset/" and args.ground_truth == "ground_truth.json"
    )
    default_available = (
        Path(args.dataset_dir).exists() and Path(args.ground_truth).exists()
    )

    if default_args_used and not default_available:
        fallback_dataset, fallback_gt = _find_latest_clean_benchmark()
        if fallback_dataset and fallback_gt:
            dataset_dir = fallback_dataset
            ground_truth = fallback_gt
            print(f"Using latest clean-import benchmark set: {ground_truth}")

    suite = BenchmarkSuite(
        dataset_dir=dataset_dir,
        ground_truth_path=ground_truth,
        engine=args.engine,
        include_non_trainable=args.include_non_trainable,
    )
    results = suite.run()

    reporter = BenchmarkReporter()
    reporter.print_terminal(results)
    md_path = f"{args.output_prefix}.md"
    json_path = f"{args.output_prefix}.json"
    reporter.save_markdown(results, md_path)
    reporter.save_json(results, json_path)
    print(f"\nSaved {md_path} and {json_path}")


def cmd_import_clean(args):
    from src.data.clean_import import run_clean_import

    summary = run_clean_import(
        source_root=args.source_root,
        output_root=args.output_root,
        copy_files=not args.no_copy,
    )

    counts = summary.get("counts", {})
    artifacts = summary.get("artifacts", {})
    print("Clean import complete.")
    print(f"Source: {summary.get('source_root')}")
    print(f"Output: {summary.get('output_root')}")
    print(f"Total .bin files: {counts.get('total_bin_files', 0)}")
    print(f"Unique parseable logs: {counts.get('unique_parseable_after_dedupe', 0)}")
    print(f"Verified labeled: {counts.get('verified_labeled', 0)}")
    print(f"Provisional labeled: {counts.get('provisional_labeled', 0)}")
    print(f"Verified unlabeled: {counts.get('verified_unlabeled', 0)}")
    print(f"Rejected non-log: {counts.get('rejected_nonlog', 0)}")
    print(f"Benchmark-trainable: {counts.get('benchmark_trainable', 0)}")
    print(f"Proof markdown: {artifacts.get('proof_markdown')}")


def cmd_collect_forum(args):
    from src.data.forum_collector import collect_forum_logs

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

    print("Forum collection complete.")
    print(f"Output root: {summary.get('output_root')}")
    print(f"Rows: {summary.get('rows', 0)}")
    print(f"Downloaded: {summary.get('downloaded', 0)}")
    print(f"Not-log payload: {summary.get('not_log_payload', 0)}")
    print(f"Download failed: {summary.get('download_failed', 0)}")
    artifacts = summary.get("artifacts", {})
    print(f"Manifest CSV: {artifacts.get('manifest_csv')}")
    print(f"Summary JSON: {artifacts.get('summary_json')}")


def cmd_mine_expert_labels(args):
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

    print("Expert-labeled forum mining complete.")
    print(f"Output root: {summary.get('output_root')}")
    print(f"Topics scanned: {summary.get('topics_scanned', 0)}")
    print(f"Topics with expert label: {summary.get('topics_with_expert_label', 0)}")
    print(f"Rows: {summary.get('rows', 0)}")
    print(f"Downloaded: {summary.get('downloaded', 0)}")
    print(f"Not-log payload: {summary.get('not_log_payload', 0)}")
    print(f"Download failed: {summary.get('download_failed', 0)}")
    artifacts = summary.get("artifacts", {})
    print(f"Manifest CSV: {artifacts.get('manifest_csv')}")
    print(f"block1 CSV: {artifacts.get('block1_csv')}")
    print(f"Summary JSON: {artifacts.get('summary_json')}")
    print(f"State JSON: {artifacts.get('state_json')}")


def cmd_batch(args):
    directory = args.directory
    if not os.path.exists(directory):
        print(f"Directory {directory} not found.")
        return

    print(f"{'File':<25} | {'Status':<15} | {'Top Diagnosis'}")
    print("-" * 65)

    pipeline = FeaturePipeline()
    engine = HybridEngine()

    for f in os.listdir(directory):
        if not f.upper().endswith(".BIN"):
            continue

        filepath = os.path.join(directory, f)
        parser = LogParser(filepath)
        parsed = parser.parse()
        features = pipeline.extract(parsed)
        diagnoses = engine.diagnose(features)

        if not diagnoses:
            status = "HEALTHY"
            top = "None"
        else:
            status = "FAIL"
            top = f"{diagnoses[0]['failure_type']} ({int(diagnoses[0]['confidence'] * 100)}%)"

        print(f"{f:<25} | {status:<15} | {top}")


def cmd_label(args):
    logfile = args.logfile
    filename = os.path.basename(logfile)

    parser = LogParser(logfile)
    parsed = parser.parse()
    pipeline = FeaturePipeline()
    features = pipeline.extract(parsed)

    engine = HybridEngine()
    diagnoses = engine.diagnose(features)

    print(f"\n--- Labeling {filename} ---")
    auto_labels = features.get("_metadata", {}).get("auto_labels", [])
    if auto_labels:
        print(f"Auto-suggested labels from ERR/EV: {auto_labels}")

    print("\nModel Predictions:")
    if diagnoses:
        for d in diagnoses:
            print(f" - {d['failure_type']} ({int(d['confidence'] * 100)}%)")
    else:
        print(" - None (Healthy)")

    print("\nEnter correct labels (comma-separated). Uses constants.VALID_LABELS.")
    print("Leave blank to skip.")
    try:
        user_input = input("Labels > ").strip()
    except EOFError:
        user_input = ""

    if not user_input:
        print("Skipped.")
        return

    labels = [l.strip() for l in user_input.split(",")]

    gt_path = "ground_truth.json"
    data = {"logs": []}
    if os.path.exists(gt_path):
        with open(gt_path, "r") as f:
            data = json.load(f)

    data["logs"] = [l for l in data.get("logs", []) if l["filename"] != filename]

    data["logs"].append(
        {
            "filename": filename,
            "labels": labels,
            "source_url": "",
            "source_type": "manual",
            "expert_quote": "",
            "confidence": "high",
        }
    )

    with open(gt_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Added {filename} to {gt_path} with labels {labels}")


def main():
    parser = argparse.ArgumentParser(description="ArduPilot Log Diagnosis Tool")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_analyze = subparsers.add_parser("analyze", help="Analyze a single log file")
    p_analyze.add_argument("logfile", help="Path to .BIN file")
    p_analyze.add_argument("--json", action="store_true", help="Output in JSON format")
    p_analyze.add_argument("-o", "--output", help="Save report to file")
    p_analyze.add_argument(
        "--no-ml", action="store_true", help="Force rule-based only diagnosis"
    )

    p_features = subparsers.add_parser(
        "features", help="Extract and print raw features"
    )
    p_features.add_argument("logfile", help="Path to .BIN file")

    p_benchmark = subparsers.add_parser("benchmark", help="Run benchmark suite")
    p_benchmark.add_argument(
        "--engine",
        choices=["rule", "ml", "hybrid"],
        default="hybrid",
        help="Engine to benchmark",
    )
    p_benchmark.add_argument(
        "--dataset-dir",
        default="dataset/",
        help="Directory containing benchmark .BIN files",
    )
    p_benchmark.add_argument(
        "--ground-truth", default="ground_truth.json", help="Ground truth JSON path"
    )
    p_benchmark.add_argument(
        "--output-prefix",
        default="benchmark_results",
        help="Output filename prefix (without extension)",
    )
    p_benchmark.add_argument(
        "--include-non-trainable",
        action="store_true",
        help="Include entries marked trainable=false",
    )

    p_batch = subparsers.add_parser("batch", help="Batch analyze directory")
    p_batch.add_argument("directory", help="Directory containing .BIN files")

    p_label = subparsers.add_parser("label", help="Interactive labeling tool")
    p_label.add_argument("logfile", help="Path to .BIN file")

    p_import = subparsers.add_parser(
        "import-clean", help="Clean import external log batch with provenance manifests"
    )
    p_import.add_argument(
        "--source-root", required=True, help="Source directory to scan"
    )
    p_import.add_argument(
        "--output-root",
        default="data/clean_imports/latest",
        help="Output directory for cleaned logs and manifests",
    )
    p_import.add_argument(
        "--no-copy",
        action="store_true",
        help="Generate manifests only, do not copy files",
    )

    p_collect = subparsers.add_parser(
        "collect-forum", help="Collect candidate logs from discuss.ardupilot.org"
    )
    p_collect.add_argument(
        "--output-root",
        default="data/raw_downloads/forum_batch",
        help="Output folder for downloaded files and manifest",
    )
    p_collect.add_argument(
        "--max-per-query",
        type=int,
        default=20,
        help="Maximum downloads per label query",
    )
    p_collect.add_argument(
        "--max-topics-per-query",
        type=int,
        default=60,
        help="Maximum forum topics scanned per query",
    )
    p_collect.add_argument(
        "--sleep-ms",
        type=int,
        default=250,
        help="Delay between download requests in milliseconds",
    )
    p_collect.add_argument("--no-zip", action="store_true", help="Skip zip attachments")
    p_collect.add_argument(
        "--queries-json", help="Path to JSON map of label->search query"
    )

    p_expert = subparsers.add_parser(
        "mine-expert-labels",
        help="Mine discuss.ardupilot.org for logs with developer-diagnosed labels",
    )
    p_expert.add_argument(
        "--output-root",
        default="data/raw_downloads/forum_expert_batch",
        help="Output folder for downloaded files and expert manifests",
    )
    p_expert.add_argument(
        "--queries-json", help="Path to JSON queries (dict/list or {label, queries[]})"
    )
    p_expert.add_argument(
        "--after-date", help="Incremental search start date (YYYY-MM-DD)"
    )
    p_expert.add_argument(
        "--max-topics-per-query",
        type=int,
        default=120,
        help="Maximum topics scanned per query",
    )
    p_expert.add_argument(
        "--max-downloads", type=int, default=300, help="Maximum downloaded payloads"
    )
    p_expert.add_argument(
        "--sleep-ms",
        type=int,
        default=300,
        help="Delay between network requests in milliseconds",
    )
    p_expert.add_argument("--no-zip", action="store_true", help="Skip zip attachments")
    p_expert.add_argument(
        "--state-path", help="Path to miner state JSON for incremental runs"
    )
    p_expert.add_argument(
        "--existing-data-root",
        default="data",
        help="Data root used to skip topics already present in labeled datasets",
    )
    p_expert.add_argument(
        "--no-skip-existing-labeled",
        action="store_true",
        help="Do not skip topic URLs already present in ground_truth files",
    )
    p_expert.add_argument(
        "--enrich-only",
        action="store_true",
        help="Only enrich an existing crawler manifest with expert labels (no new downloads)",
    )
    p_expert.add_argument(
        "--source-root",
        help="Source folder containing crawler_manifest.csv for --enrich-only mode",
    )
    p_expert.add_argument(
        "--input-manifest-name",
        default="crawler_manifest.csv",
        help="Input manifest filename for --enrich-only mode",
    )
    p_expert.add_argument(
        "--output-manifest-name",
        default="crawler_manifest_v2.csv",
        help="Output manifest filename for --enrich-only mode",
    )
    p_expert.add_argument(
        "--output-block1-name",
        default="block1_ardupilot_discuss.csv",
        help="Output block1 CSV filename for --enrich-only mode",
    )

    parsed_args = parser.parse_args()

    if parsed_args.command == "analyze":
        cmd_analyze(parsed_args)
    elif parsed_args.command == "features":
        cmd_features(parsed_args)
    elif parsed_args.command == "benchmark":
        cmd_benchmark(parsed_args)
    elif parsed_args.command == "batch":
        cmd_batch(parsed_args)
    elif parsed_args.command == "label":
        cmd_label(parsed_args)
    elif parsed_args.command == "import-clean":
        cmd_import_clean(parsed_args)
    elif parsed_args.command == "collect-forum":
        cmd_collect_forum(parsed_args)
    elif parsed_args.command == "mine-expert-labels":
        cmd_mine_expert_labels(parsed_args)


if __name__ == "__main__":
    main()
