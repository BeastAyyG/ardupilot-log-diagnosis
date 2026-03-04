#!/usr/bin/env python3
"""
Quick integration test runner — runs real .BIN files through the full pipeline.
Does NOT require pytest. Run directly: python3 tests/run_integration_check.py
"""

import sys
from pathlib import Path

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.parser.bin_parser import LogParser
from src.features.pipeline import FeaturePipeline
from src.diagnosis.hybrid_engine import HybridEngine
from src.diagnosis.decision_policy import evaluate_decision

DATA_DIR = Path("data/kaggle_backups/ardupilot-master-log-pool-v2")

# Golden logs: filename pattern → expected failure type(s)
GOLDEN_LOGS = {
    "log_0001_vibration_high": ["vibration_high"],
    "log_0009_compass_interference": ["compass_interference"],
    "log_0010_ekf_failure": ["ekf_failure"],
    "log_0008_rc_failsafe": ["rc_failsafe"],
    "log_0013_power_instability": ["power_instability", "brownout"],
    "log_0046_thrust_loss": ["thrust_loss", "mechanical_failure"],
    "log_0009_pid_tuning_issue": ["pid_tuning_issue"],
}


def run_pipeline(log_path):
    parser = LogParser(str(log_path))
    parsed = parser.parse()
    pipeline = FeaturePipeline()
    features = pipeline.extract(parsed)
    engine = HybridEngine()
    diagnoses = engine.diagnose(features)
    decision = evaluate_decision(diagnoses)
    return features, diagnoses, decision


def main():
    if not DATA_DIR.exists():
        print(f"⚠  Data directory not found: {DATA_DIR}")
        print("   Skipping integration tests (CI-safe).")
        return 0

    all_logs = sorted(DATA_DIR.glob("*.bin"))
    print(f"\n{'='*70}")
    print(f"  Integration Test: {len(all_logs)} real .BIN files")
    print(f"{'='*70}\n")

    # ── Test 1: No crashes on any log ────────────────────────────────────
    print("TEST 1: Full pipeline crash test (all logs)")
    crashes = []
    for log_path in all_logs:
        try:
            run_pipeline(log_path)
        except Exception as e:
            crashes.append((log_path.name, str(e)))

    if crashes:
        print(f"  ✗ FAILED — {len(crashes)} crash(es):")
        for name, err in crashes:
            print(f"    {name}: {err}")
    else:
        print(f"  ✓ PASSED — {len(all_logs)} logs, 0 crashes")

    # ── Test 2: Golden log accuracy ──────────────────────────────────────
    print(f"\nTEST 2: Golden log accuracy ({len(GOLDEN_LOGS)} golden logs)")
    correct = 0
    total = 0
    failures = []

    for pattern, expected_types in GOLDEN_LOGS.items():
        matches = list(DATA_DIR.glob(f"*{pattern}*"))
        if not matches:
            print(f"  ⚠ Skipped: no log matching '{pattern}'")
            continue

        log_path = matches[0]
        total += 1

        try:
            _, diagnoses, decision = run_pipeline(log_path)
            predicted = [d["failure_type"] for d in diagnoses]

            hit = any(exp in predicted for exp in expected_types)
            if hit:
                correct += 1
                top = diagnoses[0] if diagnoses else {}
                print(f"  ✓ {log_path.name}")
                print(f"    Expected: {expected_types}")
                print(f"    Got:      {predicted}")
                print(f"    Top conf: {top.get('confidence', 0):.2f} via {top.get('detection_method', '?')}")
            else:
                failures.append((log_path.name, expected_types, predicted))
                print(f"  ✗ {log_path.name}")
                print(f"    Expected: {expected_types}")
                print(f"    Got:      {predicted}")
        except Exception as e:
            failures.append((log_path.name, expected_types, f"CRASH: {e}"))
            print(f"  ✗ {log_path.name} — CRASH: {e}")

    accuracy = correct / total if total > 0 else 0
    print(f"\n  Golden Log Accuracy: {correct}/{total} = {accuracy:.0%}")

    # ── Test 3: Schema compliance ────────────────────────────────────────
    print("\nTEST 3: Output schema compliance (sample of 10 logs)")
    schema_errors = []
    for log_path in all_logs[:10]:
        try:
            _, diagnoses, decision = run_pipeline(log_path)
            for d in diagnoses:
                for key in ["failure_type", "confidence", "evidence", "recommendation"]:
                    if key not in d:
                        schema_errors.append(f"{log_path.name}: missing '{key}'")
                if not d.get("evidence"):
                    schema_errors.append(f"{log_path.name}: empty evidence for {d.get('failure_type')}")
            for key in ["status", "requires_human_review", "top_guess"]:
                if key not in decision:
                    schema_errors.append(f"{log_path.name}: decision missing '{key}'")
        except Exception as e:
            schema_errors.append(f"{log_path.name}: CRASH: {e}")

    if schema_errors:
        print(f"  ✗ FAILED — {len(schema_errors)} error(s):")
        for err in schema_errors[:5]:
            print(f"    {err}")
    else:
        print("  ✓ PASSED — all outputs have complete schema")

    # ── Summary ──────────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print("  SUMMARY")
    print(f"  Crash test:    {'PASS' if not crashes else 'FAIL'}")
    print(f"  Golden logs:   {correct}/{total} = {accuracy:.0%}")
    print(f"  Schema:        {'PASS' if not schema_errors else 'FAIL'}")
    print(f"{'='*70}\n")

    return 0 if (not crashes and not schema_errors) else 1


if __name__ == "__main__":
    sys.exit(main())
