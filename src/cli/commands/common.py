from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Sequence

from src.features.pipeline import FeaturePipeline
from src.parser.bin_parser import LogParser
from src.parser.file_format import detect_file_format, supported_format_kinds
from src.analysis.windowing import extract_ml_feature_candidates


def print_explain_box(
    explain_data: dict[str, Any] | None, final_diagnoses: Sequence[dict[str, Any]]
) -> None:
    if not explain_data:
        return

    print("")
    print("Hybrid Engine Arbitration Breakdown")
    print("-----------------------------------")

    rule_best = explain_data.get("rule", [None])[0] if explain_data.get("rule") else None
    if rule_best:
        print(
            f"Rule Engine: {rule_best['failure_type']} "
            f"({rule_best['confidence'] * 100:.0f}%)"
        )
    else:
        print("Rule Engine: healthy (0%)")

    ml_best = explain_data.get("ml", [None])[0] if explain_data.get("ml") else None
    if ml_best:
        print(
            f"XGBoost ML: {ml_best['failure_type']} "
            f"({ml_best['confidence'] * 100:.0f}%)"
        )
    else:
        print("XGBoost ML: healthy (0%)")

    if final_diagnoses:
        final_best = final_diagnoses[0]
        print(
            f"Final Result: {final_best['failure_type']} "
            f"({final_best['confidence'] * 100:.0f}%)"
        )
    else:
        print("Final Result: healthy")

    hypotheses = explain_data.get("hypotheses", [])
    arbiter = explain_data.get("causal_arbiter", {})
    if hypotheses:
        print("")
        print("Hypothesis Scaffolding:")
        for idx, item in enumerate(hypotheses[:3], start=1):
            tanomaly = item.get("tanomaly", -1.0)
            time_text = (
                f"T+{tanomaly / 1e6:.1f}s"
                if isinstance(tanomaly, (int, float)) and tanomaly > 0
                else "no onset timestamp"
            )
            print(
                f"  Hypothesis {idx}: {item['failure_type']} via {item['source']} "
                f"({item['merged_confidence'] * 100:.0f}%) from "
                f"{item.get('lead_feature') or 'telemetry correlation'} at {time_text}."
            )
        if arbiter:
            print(f"  Causal Arbiter: {arbiter.get('reason', 'no arbiter summary')}")


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


def load_parsed_and_features(logfile: str) -> tuple[dict[str, Any], dict[str, Any]]:
    parser = LogParser(logfile)
    parsed = parser.parse()
    pipeline = FeaturePipeline()
    return parsed, pipeline.extract(parsed)


def load_features(logfile: str) -> dict[str, Any]:
    _, features = load_parsed_and_features(logfile)
    return features


def diagnose_with_windowed_ml(
    engine: Any, parsed: dict[str, Any], features: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Use the artifact's training-time window contract when ML is available."""
    classifier = getattr(engine, "ml", None)
    window_config = (
        classifier.get_inference_window_config()
        if getattr(classifier, "available", False)
        else {}
    )
    if not getattr(classifier, "available", False) or not window_config.get("verified", False):
        return engine.diagnose(features), {
            "aggregation": "full_log",
            "candidate_count": 1,
            "source": (
                "legacy_model_window_contract_missing"
                if getattr(classifier, "available", False)
                else "rule_only_or_ml_unavailable"
            ),
        }

    pipeline = FeaturePipeline()
    window_features, info = extract_ml_feature_candidates(
        parsed,
        pipeline,
        window_config,
        full_features=features,
    )
    return engine.diagnose(features, window_features=window_features), info


def ensure_extraction_success(logfile: str, features: dict[str, Any]) -> None:
    path = Path(logfile)
    if path.exists():
        detected = detect_file_format(path)
        if detected.get("format") in {"text_log", "px4_ulog", "mavlink_tlog", "betaflight_bbl"} and not detected.get("supported", False):
            print("\n[ERROR] UNSUPPORTED_FORMAT")
            print(f"  Detected: {detected.get('format_name', 'unknown format')}")
            print(f"  Runtime-supported adapters: {', '.join(supported_format_kinds()) or 'none'}")
            if detected.get("unsupported_reason"):
                print(f"  Reason: {detected['unsupported_reason']}")
            print("  Use `python -m src.cli.main capabilities` to inspect the capability registry.")
            sys.exit(2)
    metadata = features.get("_metadata", {})
    if metadata.get("extraction_success", True):
        return

    print("\n[ERROR] EXTRACTION_FAILED")
    print(f"  Log file:  {logfile}")
    print(f"  Duration:  {metadata.get('duration_sec', 0):.0f}s")
    print(f"  Messages:  {metadata.get('messages_found', [])}")
    print("  This log appears to be empty or corrupt. No diagnosis produced.")
    print("  Verify the file is a valid supported flight log (ArduPilot .BIN/.LOG, PX4 .ULG/.ULOG, MAVLink .TLOG, or optional Blackbox .BBL/.BFL).")
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
