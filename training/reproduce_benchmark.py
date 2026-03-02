"""
One-command reproducibility script for the ArduPilot Log Diagnosis benchmark.

This script reproduces the full benchmark pipeline from a clean environment:
  1. Validate prerequisites (data directories, ground truth JSON, Python deps).
  2. Optionally retrain the ML model from scratch (--from-scratch).
  3. Run the benchmark suite (rule, hybrid engines).
  4. Print a summary and assert minimum F1 targets.
  5. Write a reproducibility report to docs/reproducibility_report.md.

Usage:
    python training/reproduce_benchmark.py
    python training/reproduce_benchmark.py --from-scratch
    python training/reproduce_benchmark.py --dataset-dir data/master_pool/dataset \\
        --ground-truth data/master_pool/ground_truth.json
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# ── Minimum metric targets ───────────────────────────────────────────────────
MIN_PARSE_RATE = 0.97        # ≥ 97% logs must extract successfully
MIN_COMPASS_RECALL = 0.85    # compass_interference recall
MIN_VIBRATION_RECALL = 0.80  # vibration_high recall
MIN_EKF_F1 = 0.50            # ekf_failure F1
MIN_MACRO_F1 = 0.30          # overall macro F1 (conservative given label imbalance)


def _run(cmd: list, desc: str) -> int:
    """Run a subprocess command, stream stdout, return exit code."""
    print(f"\n{'─'*60}")
    print(f"  ▶  {desc}")
    print(f"{'─'*60}")
    result = subprocess.run(cmd, cwd=str(ROOT_DIR))
    return result.returncode


def _check_prerequisites(dataset_dir: Path, ground_truth: Path) -> list:
    """Return list of missing prerequisite descriptions."""
    missing = []

    if not dataset_dir.exists():
        missing.append(f"Dataset directory not found: {dataset_dir}")
    else:
        bin_files = list(dataset_dir.glob("*.bin")) + list(dataset_dir.glob("*.BIN"))
        if not bin_files:
            missing.append(f"No .BIN files found in {dataset_dir}")

    if not ground_truth.exists():
        missing.append(f"Ground truth JSON not found: {ground_truth}")
    else:
        try:
            with open(ground_truth) as f:
                gt = json.load(f)
            logs = gt.get("logs", [])
            if not logs:
                missing.append("ground_truth.json has no 'logs' entries")
        except json.JSONDecodeError:
            missing.append(f"ground_truth.json contains invalid JSON: {ground_truth}")

    return missing


def _retrain_model() -> bool:
    """Retrain the ML model. Returns True on success."""
    # Step 1: rebuild dataset CSVs
    rc = _run(
        [sys.executable, "training/build_dataset.py"],
        "Step 1 of 2: Rebuild feature/label CSVs (build_dataset.py)",
    )
    if rc != 0:
        print("  ❌  build_dataset.py failed — aborting retraining.")
        return False

    # Step 2: train model
    rc = _run(
        [sys.executable, "training/train_model.py"],
        "Step 2 of 2: Train model with SMOTE + GridSearchCV + calibration (train_model.py)",
    )
    if rc != 0:
        print("  ❌  train_model.py failed — model artifacts may be stale.")
        return False

    return True


def _run_benchmark(dataset_dir: Path, ground_truth: Path, engine: str, output_prefix: str) -> dict:
    """Run benchmark suite and return parsed metrics dict."""
    from src.benchmark.suite import BenchmarkSuite
    from src.benchmark.reporter import BenchmarkReporter

    suite = BenchmarkSuite(
        dataset_dir=str(dataset_dir),
        ground_truth_path=str(ground_truth),
        engine=engine,
        include_non_trainable=False,
    )
    results = suite.run()

    reporter = BenchmarkReporter()
    reporter.print_terminal(results)
    reporter.save_json(results, f"{output_prefix}_{engine}.json")
    reporter.save_markdown(results, f"{output_prefix}_{engine}.md")

    return results.compute_metrics()


def _check_targets(metrics: dict, engine_label: str) -> list:
    """Return list of failed target descriptions."""
    ov = metrics.get("overall", {})
    per_label = metrics.get("per_label", {})
    failures = []

    total = ov.get("total_logs", 0)
    extracted = ov.get("successful_extractions", 0)
    if total > 0 and (extracted / total) < MIN_PARSE_RATE:
        failures.append(
            f"[{engine_label}] Parse rate {extracted}/{total} "
            f"({100*extracted/total:.1f}%) < {100*MIN_PARSE_RATE:.0f}%"
        )

    macro_f1 = ov.get("macro_f1", 0.0)
    if macro_f1 < MIN_MACRO_F1:
        failures.append(
            f"[{engine_label}] Macro F1 {macro_f1:.3f} < {MIN_MACRO_F1:.2f}"
        )

    # Per-label recall checks (recall = tp / support when support > 0)
    label_checks = [
        ("compass_interference", MIN_COMPASS_RECALL, "compass recall"),
        ("vibration_high", MIN_VIBRATION_RECALL, "vibration recall"),
        ("ekf_failure", MIN_EKF_F1, "EKF F1"),
    ]
    for label, threshold, name in label_checks:
        lm = per_label.get(label, {})
        if lm.get("support", 0) > 0:
            val = lm.get("recall" if label != "ekf_failure" else "f1", 0.0)
            if val < threshold:
                failures.append(
                    f"[{engine_label}] {name} {val:.3f} < {threshold:.2f}"
                )

    return failures


def _write_report(
    results_by_engine: dict,
    target_failures: list,
    retrained: bool,
    elapsed: float,
    output_path: Path,
):
    """Write a markdown reproducibility report."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        "# Reproducibility Report — ArduPilot Log Diagnosis",
        "",
        f"**Generated**: {timestamp}  ",
        f"**Elapsed**: {elapsed:.1f}s  ",
        f"**Retrained from scratch**: {'Yes' if retrained else 'No'}  ",
        "",
        "## Benchmark Results",
        "",
    ]

    for engine, metrics in results_by_engine.items():
        ov = metrics.get("overall", {})
        macro_f1 = ov.get("macro_f1", 0.0)
        total = ov.get("total_logs", 0)
        extracted = ov.get("successful_extractions", 0)
        parse_pct = 100 * extracted / max(total, 1)
        lines += [
            f"### Engine: `{engine}`",
            "",
            f"| Metric | Value |",
            f"|---|---|",
            f"| Total logs | {total} |",
            f"| Extracted | {extracted} ({parse_pct:.1f}%) |",
            f"| Macro F1 | {macro_f1:.3f} |",
        ]
        per_label = metrics.get("per_label", {})
        for label, lm in per_label.items():
            if lm.get("support", 0) > 0 or lm.get("fp", 0) > 0:
                lines.append(
                    f"| {label} F1 | {lm.get('f1', 0.0):.3f} |"
                )
        lines.append("")

    lines += ["## Target Gate Results", ""]
    if target_failures:
        lines.append("❌ **Some targets FAILED:**")
        lines.append("")
        for f in target_failures:
            lines.append(f"- {f}")
    else:
        lines.append("✅ **All targets PASSED**")
    lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines))
    print(f"\nReproducibility report saved → {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Reproduce ArduPilot Log Diagnosis benchmark from clean environment."
    )
    parser.add_argument(
        "--from-scratch",
        action="store_true",
        help="Rebuild dataset CSVs and retrain ML model before benchmarking",
    )
    parser.add_argument(
        "--dataset-dir",
        default=None,
        help="Directory containing .BIN log files (default: auto-detected)",
    )
    parser.add_argument(
        "--ground-truth",
        default=None,
        help="Path to ground_truth.json (default: auto-detected)",
    )
    parser.add_argument(
        "--output-prefix",
        default="reproduce_benchmark_results",
        help="Output file prefix for JSON/MD benchmark results",
    )
    parser.add_argument(
        "--report-path",
        default="docs/reproducibility_report.md",
        help="Path for the reproducibility report markdown",
    )
    args = parser.parse_args()

    start_time = time.time()
    print("=" * 60)
    print("  ArduPilot Log Diagnosis — Reproducibility Check")
    print("=" * 60)

    # ── Resolve dataset / ground truth paths ────────────────────────────────
    if args.dataset_dir and args.ground_truth:
        dataset_dir = Path(args.dataset_dir)
        ground_truth = Path(args.ground_truth)
    else:
        # Auto-detect from standard locations
        candidates = [
            (
                ROOT_DIR / "data/master_pool/dataset",
                ROOT_DIR / "data/master_pool/ground_truth.json",
            ),
            (
                ROOT_DIR / "dataset",
                ROOT_DIR / "ground_truth.json",
            ),
        ]
        dataset_dir = ground_truth = None
        for d, g in candidates:
            if d.exists() and g.exists():
                dataset_dir = d
                ground_truth = g
                break

        if dataset_dir is None:
            # Try clean_imports fallback
            root = ROOT_DIR / "data/clean_imports"
            if root.exists():
                candidates_gt = sorted(
                    root.glob("*/benchmark_ready/ground_truth.json"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )
                if candidates_gt:
                    ground_truth = candidates_gt[0]
                    dataset_dir = ground_truth.parent / "dataset"

        if dataset_dir is None or ground_truth is None:
            print(
                "\n❌  No dataset found. Please provide --dataset-dir and --ground-truth,\n"
                "    or populate data/master_pool/ (see docs/DATA_INVENTORY.md)."
            )
            sys.exit(2)

    print(f"\nDataset directory : {dataset_dir}")
    print(f"Ground truth      : {ground_truth}")

    # ── Prerequisite checks ─────────────────────────────────────────────────
    missing = _check_prerequisites(dataset_dir, ground_truth)
    if missing:
        print("\n❌  Prerequisites not met:")
        for m in missing:
            print(f"  - {m}")
        sys.exit(2)

    # ── Optional retrain ─────────────────────────────────────────────────────
    retrained = False
    if args.from_scratch:
        print("\n── Retraining from scratch ──────────────────────────────────")
        retrained = _retrain_model()
        if not retrained:
            print("\n⚠️  Retraining failed. Continuing benchmark with existing artifacts.")

    # ── Run benchmark for each engine ────────────────────────────────────────
    engines = ["rule", "hybrid"]
    results_by_engine = {}
    all_target_failures = []

    for engine in engines:
        print(f"\n── Benchmarking engine: {engine} ───────────────────────────")
        metrics = _run_benchmark(dataset_dir, ground_truth, engine, args.output_prefix)
        results_by_engine[engine] = metrics
        failures = _check_targets(metrics, engine)
        all_target_failures.extend(failures)

    # ── Summary ──────────────────────────────────────────────────────────────
    elapsed = time.time() - start_time
    print("\n" + "=" * 60)
    print("  REPRODUCIBILITY SUMMARY")
    print("=" * 60)

    for engine, metrics in results_by_engine.items():
        ov = metrics.get("overall", {})
        total = ov.get("total_logs", 0)
        extracted = ov.get("successful_extractions", 0)
        parse_pct = 100 * extracted / max(total, 1)
        macro_f1 = ov.get("macro_f1", 0.0)
        print(
            f"  [{engine:6s}] Logs: {extracted}/{total} ({parse_pct:.0f}%)  "
            f"Macro F1: {macro_f1:.3f}"
        )

    print(f"\n  Total time: {elapsed:.1f}s")

    _write_report(results_by_engine, all_target_failures, retrained, elapsed, Path(args.report_path))

    if all_target_failures:
        print("\n❌  Target failures:")
        for f in all_target_failures:
            print(f"  - {f}")
        print(
            "\n  ⚠️  One or more benchmark targets were not met.\n"
            "  This may indicate model degradation or data issues.\n"
            "  See docs/UPGRADE_ROADMAP.md for remediation steps."
        )
        sys.exit(1)
    else:
        print("\n✅  All benchmark targets passed. Reproducibility confirmed.")
        sys.exit(0)


if __name__ == "__main__":
    main()
