"""
Firmware Regression Sentinel
=============================
Detects rising failure patterns across successive benchmark runs.

Usage:
    python training/regression_sentinel.py results_old.json results_new.json [...]

Each JSON file is a benchmark_results.json produced by `python -m src.cli.main benchmark`.
Files should be supplied in chronological order (oldest first).

The sentinel prints a warning if any failure label's prediction rate has risen
by more than RISE_THRESHOLD between the first and last run.
"""

import json
import sys
from collections import Counter
from pathlib import Path


RISE_THRESHOLD = 0.10   # 10 percentage-point rise triggers a warning
MIN_SAMPLES = 5          # minimum samples required to flag a trend


def _load_results(path: str) -> dict:
    with open(path, "r") as f:
        content = f.read().strip()
    if not content:
        return {"_empty": True}
    return json.loads(content)


def _label_rates(data: dict) -> dict:
    """
    Extract per-label prediction rates from a benchmark result dict.
    Supports two formats:
      1. Flat list of {predicted_label, ...} objects (legacy / batch output)
      2. Benchmark JSON with 'per_label': {label: {tp, fp, fn, support, ...}}
    """
    if data.get("_empty"):
        return {}

    # Format 1: flat list
    if isinstance(data, list):
        total = len(data)
        if total == 0:
            return {}
        counts: Counter = Counter()
        for r in data:
            pred = r.get("predicted_label") or r.get("top_diagnosis") or "healthy"
            counts[pred] += 1
        return {label: count / total for label, count in counts.items()}

    # Format 2: benchmark JSON with per_label stats
    per_label = data.get("per_label", {})
    if per_label:
        # total predictions = sum of (tp + fp) per label
        total_preds = sum(
            v.get("tp", 0) + v.get("fp", 0) for v in per_label.values()
        )
        if total_preds == 0:
            # Fall back to support if no predictions were made
            total_preds = sum(v.get("support", 0) for v in per_label.values())
        if total_preds == 0:
            return {}
        return {
            label: (v.get("tp", 0) + v.get("fp", 0)) / total_preds
            for label, v in per_label.items()
        }

    # Format 3: flat results list nested under "results" key
    results = data.get("results", [])
    return _label_rates(results)


def run_sentinel(result_files: list) -> dict:
    """
    Compare label rates across runs and return a dict with:
      - 'rising'  : list of (label, old_rate, new_rate, delta) that crossed RISE_THRESHOLD
      - 'stable'  : labels with no significant change
      - 'files'   : files analysed
    """
    if len(result_files) < 2:
        return {"error": "Need at least 2 result files to detect trends.", "files": result_files}

    run_rates = []
    for path in result_files:
        data = _load_results(path)
        rates = _label_rates(data)
        # n_samples: prefer overall.total_logs; fall back to sum of support
        n = 0
        if isinstance(data, dict):
            n = data.get("overall", {}).get("total_logs", 0)
            if n == 0:
                per_label = data.get("per_label", {})
                n = sum(v.get("support", 0) for v in per_label.values())
        elif isinstance(data, list):
            n = len(data)
        run_rates.append((path, rates, n))

    first_path, first_rates, first_n = run_rates[0]
    last_path, last_rates, last_n = run_rates[-1]

    all_labels = set(first_rates) | set(last_rates)

    rising = []
    stable = []

    for label in sorted(all_labels):
        old = first_rates.get(label, 0.0)
        new = last_rates.get(label, 0.0)
        delta = new - old
        # Only flag if either run had enough samples
        if (first_n >= MIN_SAMPLES or last_n >= MIN_SAMPLES) and delta >= RISE_THRESHOLD:
            rising.append({"label": label, "old_rate": round(old, 3), "new_rate": round(new, 3), "delta": round(delta, 3)})
        else:
            stable.append(label)

    return {
        "files": [str(p) for p in result_files],
        "first_run": {"file": str(first_path), "n": first_n, "rates": first_rates},
        "last_run": {"file": str(last_path), "n": last_n, "rates": last_rates},
        "rising": rising,
        "stable": stable,
        "rise_threshold": RISE_THRESHOLD,
    }


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    files = sys.argv[1:]
    # Validate all files exist
    for f in files:
        if not Path(f).exists():
            print(f"[ERROR] File not found: {f}")
            sys.exit(1)

    report = run_sentinel(files)

    if "error" in report:
        print(f"[ERROR] {report['error']}")
        sys.exit(1)

    print("=" * 60)
    print("  Firmware Regression Sentinel")
    print("=" * 60)
    print(f"  First run : {report['first_run']['file']} (n={report['first_run']['n']})")
    print(f"  Last run  : {report['last_run']['file']} (n={report['last_run']['n']})")
    print(f"  Threshold : +{int(RISE_THRESHOLD * 100)}pp rise")
    print()

    if not report["rising"]:
        print("✓ No rising failure patterns detected.")
    else:
        print(f"⚠  {len(report['rising'])} RISING PATTERN(S) DETECTED:")
        for item in report["rising"]:
            old_pct = int(item["old_rate"] * 100)
            new_pct = int(item["new_rate"] * 100)
            delta_pct = int(item["delta"] * 100)
            print(f"   [{delta_pct:+d}pp] {item['label']}: {old_pct}% → {new_pct}%")

    if report["stable"]:
        print(f"\nStable labels: {', '.join(report['stable'])}")


if __name__ == "__main__":
    main()
