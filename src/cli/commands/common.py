from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Sequence

from src.features.pipeline import FeaturePipeline
from src.parser.bin_parser import LogParser


def print_explain_box(explain_data: dict[str, Any] | None, final_diagnoses: Sequence[dict[str, Any]]) -> None:
    if not explain_data:
        return

    print("")
    print("╔════════════════════════════════════════════════════════╗")
    print("║  Hybrid Engine Arbitration Breakdown                  ║")
    print("╠════════════════════════════════════════════════════════╣")

    rule_best = explain_data["rule"][0] if explain_data.get("rule") else None
    print("║  [Rule Engine]                                         ║")
    if rule_best:
        print(
            f"║  Top Guess: {rule_best['failure_type'].upper():<27} ({rule_best['confidence'] * 100:3.0f}%) ║"
        )
    else:
        print(f"║  Top Guess: {'HEALTHY':<27} (  0%) ║")
    print("║                                                        ║")

    ml_best = explain_data["ml"][0] if explain_data.get("ml") else None
    print("║  [XGBoost ML Model]                                    ║")
    if ml_best:
        print(
            f"║  Top Guess: {ml_best['failure_type'].upper():<27} ({ml_best['confidence'] * 100:3.0f}%) ║"
        )
    else:
        print(f"║  Top Guess: {'HEALTHY':<27} (  0%) ║")
    print("║                                                        ║")

    print("║  [Final Fused Decision]                                ║")
    if final_diagnoses:
        final_best = final_diagnoses[0]
        print(
            f"║  Result:    {final_best['failure_type'].upper():<27} ({final_best['confidence'] * 100:3.0f}%) ║"
        )
    else:
        print("║  Result:    HEALTHY                                    ║")

    print("╚════════════════════════════════════════════════════════╝")


def find_latest_clean_benchmark() -> tuple[str | None, str | None]:
    root = Path("data/clean_imports")
    if not root.exists():
        return None, None

    candidates = sorted(
        root.glob("*/benchmark_ready/ground_truth.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return None, None

    gt_path = candidates[0]
    dataset_dir = gt_path.parent / "dataset"
    if not dataset_dir.exists():
        return None, None

    return str(dataset_dir), str(gt_path)


def load_features(logfile: str) -> dict[str, Any]:
    parser = LogParser(logfile)
    parsed = parser.parse()
    pipeline = FeaturePipeline()
    return pipeline.extract(parsed)


def ensure_extraction_success(logfile: str, features: dict[str, Any]) -> None:
    metadata = features.get("_metadata", {})
    if metadata.get("extraction_success", True):
        return

    print("\n[ERROR] EXTRACTION_FAILED")
    print(f"  Log file:  {logfile}")
    print(f"  Duration:  {metadata.get('duration_sec', 0):.0f}s")
    print(f"  Messages:  {metadata.get('messages_found', [])}")
    print("  This log appears to be empty or corrupt. No diagnosis produced.")
    print("  Verify the file is a valid ArduPilot .BIN dataflash log.")
    sys.exit(2)


def write_or_print_output(output: str, output_path: str | None, saved_label: str) -> None:
    if output_path:
        with open(output_path, "w", encoding="utf-8") as file_obj:
            file_obj.write(output)
        print(f"{saved_label} saved to {output_path}")
    else:
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except AttributeError:
            pass
        print(output)


def print_json(data: Any) -> None:
    print(json.dumps(data, indent=2))
