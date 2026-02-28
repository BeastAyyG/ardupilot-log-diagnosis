"""
Measure False Critical Rate (FCR) for the hybrid diagnosis engine.

FCR = (number of CRITICAL diagnoses on verified-healthy logs) / (total healthy logs)

A healthy log is one verified to have no known failures. FCR > 10% means the tool
is "crying wolf", which degrades maintainer trust faster than low recall does.

Target: FCR ≤ 10% (production gate).

Usage:
    python training/measure_fcr.py --healthy-dir data/healthy_reference_set/
    python training/measure_fcr.py --healthy-dir <dir> --target-fcr 0.10
"""

import argparse
import json
import sys
from pathlib import Path

from src.parser.bin_parser import LogParser
from src.features.pipeline import FeaturePipeline
from src.diagnosis.hybrid_engine import HybridEngine
from src.diagnosis.decision_policy import evaluate_decision

FCR_PASS_THRESHOLD = 0.10


def measure_fcr(healthy_dir: str, target_fcr: float, verbose: bool) -> float:
    dir_path = Path(healthy_dir)
    if not dir_path.exists():
        print(f"ERROR: Healthy reference directory not found: {healthy_dir}")
        print(
            "Create a directory of manually verified healthy logs and pass it via --healthy-dir.\n"
            "Example: data/healthy_reference_set/\n"
            "These logs must have no known failures (no labels in ground_truth)."
        )
        sys.exit(2)

    bin_files = sorted(dir_path.glob("*.bin")) + sorted(dir_path.glob("*.BIN"))
    if not bin_files:
        print(f"No .BIN files found in {healthy_dir}")
        sys.exit(2)

    print(f"Evaluating {len(bin_files)} healthy reference logs...\n")

    pipeline = FeaturePipeline()
    engine = HybridEngine()
    false_criticals = []
    errors = []

    for f in bin_files:
        try:
            parsed = LogParser(str(f)).parse()
            features = pipeline.extract(parsed)
            diagnoses = engine.diagnose(features)
            decision = evaluate_decision(diagnoses)

            has_critical = any(
                d.get("severity", "") == "critical" for d in diagnoses
            )
            if has_critical:
                false_criticals.append({
                    "file": f.name,
                    "diagnoses": [
                        {"failure_type": d["failure_type"], "confidence": d["confidence"]}
                        for d in diagnoses if d.get("severity") == "critical"
                    ],
                })
                if verbose:
                    print(f"  ⚠️  FALSE CRITICAL: {f.name}")
                    for d in diagnoses:
                        if d.get("severity") == "critical":
                            print(f"     → {d['failure_type']} ({d['confidence']:.0%})")
            else:
                if verbose:
                    print(f"  ✅ {f.name} — clean")

        except Exception as e:
            errors.append({"file": f.name, "error": str(e)})
            if verbose:
                print(f"  ⛔ {f.name} — parse error: {e}")

    total = len(bin_files)
    fcr = len(false_criticals) / total if total > 0 else 0.0

    print(f"\n{'='*55}")
    print(f"  FCR Result: {len(false_criticals)} / {total} healthy logs flagged")
    print(f"  FCR:        {fcr:.1%}")
    print(f"  Target:     ≤ {target_fcr:.0%}")
    if fcr <= target_fcr:
        print(f"  Result:     ✅ PASS")
    else:
        print(f"  Result:     ❌ FAIL — FCR exceeds production threshold")
    if errors:
        print(f"  Parse errors: {len(errors)} (excluded from FCR)")
    print(f"{'='*55}\n")

    report = {
        "total_healthy_logs": total,
        "false_criticals": len(false_criticals),
        "fcr": fcr,
        "target_fcr": target_fcr,
        "pass": fcr <= target_fcr,
        "false_critical_details": false_criticals,
        "parse_errors": errors,
    }
    report_path = "training/fcr_report.json"
    with open(report_path, "w") as fp:
        json.dump(report, fp, indent=2)
    print(f"FCR report saved → {report_path}")

    return fcr


def main():
    parser = argparse.ArgumentParser(description="Measure False Critical Rate (FCR)")
    parser.add_argument(
        "--healthy-dir",
        default="data/healthy_reference_set",
        help="Directory of verified healthy .BIN logs",
    )
    parser.add_argument(
        "--target-fcr",
        type=float,
        default=FCR_PASS_THRESHOLD,
        help=f"FCR pass threshold (default {FCR_PASS_THRESHOLD})",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Print per-file results"
    )
    args = parser.parse_args()

    fcr = measure_fcr(args.healthy_dir, args.target_fcr, args.verbose)
    sys.exit(0 if fcr <= args.target_fcr else 1)


if __name__ == "__main__":
    main()
