from __future__ import annotations

import sys
from argparse import _SubParsersAction
from pathlib import Path

from src.benchmark.reporter import BenchmarkReporter
from src.benchmark.suite import BenchmarkSuite

from .common import find_latest_clean_benchmark


def register(subparsers: _SubParsersAction) -> None:
    parser = subparsers.add_parser("benchmark", help="Run benchmark suite")
    parser.add_argument("--engine", choices=["rule", "ml", "hybrid"], default="hybrid", help="Engine to benchmark")
    parser.add_argument("--dataset-dir", default="dataset/", help="Directory containing benchmark .BIN files")
    parser.add_argument("--ground-truth", default="ground_truth.json", help="Ground truth JSON path")
    parser.add_argument("--output-prefix", default="benchmark_results", help="Output filename prefix (without extension)")
    parser.add_argument("--include-non-trainable", action="store_true", help="Include entries marked trainable=false")
    parser.add_argument(
        "--assert-min-f1",
        type=float,
        default=None,
        metavar="THRESHOLD",
        help="Fail with exit code 1 if overall macro F1 is below this threshold.",
    )
    parser.set_defaults(func=run)


def run(args) -> None:
    dataset_dir = args.dataset_dir
    ground_truth = args.ground_truth

    default_args_used = args.dataset_dir == "dataset/" and args.ground_truth == "ground_truth.json"
    default_available = Path(args.dataset_dir).exists() and Path(args.ground_truth).exists()

    if default_args_used and not default_available:
        fallback_dataset, fallback_gt = find_latest_clean_benchmark()
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

    if args.assert_min_f1 is not None:
        metrics = results.compute_metrics()
        macro_f1 = metrics.get("overall", {}).get("macro_f1", 0.0)
        if macro_f1 < args.assert_min_f1:
            print(f"\nMacro F1 {macro_f1:.3f} is below required minimum {args.assert_min_f1:.2f}.")
            sys.exit(1)
        print(f"\nMacro F1 {macro_f1:.3f} meets the minimum requirement {args.assert_min_f1:.2f}.")
