#!/usr/bin/env python3
"""Run ML, hybrid, and rule benchmarks in one command."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path


def _load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _run_engine(engine: str, dataset_dir: Path, ground_truth: Path, output_prefix: Path) -> None:
    cmd = [
        sys.executable,
        "-m",
        "src.cli.main",
        "benchmark",
        "--engine",
        engine,
        "--dataset-dir",
        str(dataset_dir),
        "--ground-truth",
        str(ground_truth),
        "--output-prefix",
        str(output_prefix),
    ]
    print(f"Running: {shlex.join(cmd)}")
    subprocess.run(cmd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run all benchmark engines")
    parser.add_argument(
        "--dataset-dir",
        default="data/final_training_dataset_2026-02-23/dataset",
        help="Directory containing .BIN logs",
    )
    parser.add_argument(
        "--ground-truth",
        default="data/final_training_dataset_2026-02-23/ground_truth.json",
        help="Ground-truth JSON path",
    )
    parser.add_argument(
        "--output-dir",
        default="data/final_training_dataset_2026-02-23",
        help="Directory where benchmark outputs are written",
    )
    parser.add_argument(
        "--output-stem",
        default="benchmark_results",
        help="Output filename stem (engine suffix is appended)",
    )
    parser.add_argument(
        "--engines",
        nargs="+",
        default=["ml", "hybrid", "rule"],
        choices=["ml", "hybrid", "rule"],
        help="Benchmark engines to run",
    )
    args = parser.parse_args()

    dataset_dir = Path(args.dataset_dir)
    ground_truth = Path(args.ground_truth)
    output_dir = Path(args.output_dir)

    if not dataset_dir.exists():
        raise FileNotFoundError(f"Dataset dir not found: {dataset_dir}")
    if not ground_truth.exists():
        raise FileNotFoundError(f"Ground truth file not found: {ground_truth}")

    output_dir.mkdir(parents=True, exist_ok=True)

    summaries = []
    for engine in args.engines:
        output_prefix = output_dir / f"{args.output_stem}_{engine}"
        _run_engine(engine, dataset_dir, ground_truth, output_prefix)

        json_path = Path(f"{output_prefix}.json")
        if not json_path.exists():
            raise FileNotFoundError(f"Expected benchmark output missing: {json_path}")

        overall = _load_json(json_path).get("overall", {})
        summaries.append(
            {
                "engine": engine,
                "accuracy": float(overall.get("accuracy", 0.0)),
                "macro_f1": float(overall.get("macro_f1", 0.0)),
                "total_logs": int(overall.get("total_logs", 0)),
                "successful_extractions": int(overall.get("successful_extractions", 0)),
                "failed_extractions": int(overall.get("failed_extractions", 0)),
                "output": str(json_path),
            }
        )

    print("\nRun complete")
    for row in summaries:
        print(
            f"{row['engine']}: "
            f"accuracy={row['accuracy']:.4f}, "
            f"macro_f1={row['macro_f1']:.4f}, "
            f"logs={row['total_logs']}, "
            f"ok={row['successful_extractions']}, "
            f"failed={row['failed_extractions']}"
        )
        print(f"  output={row['output']}")


if __name__ == "__main__":
    main()
