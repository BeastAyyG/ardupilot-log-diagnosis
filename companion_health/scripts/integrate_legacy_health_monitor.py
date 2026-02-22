#!/usr/bin/env python3
"""Import and validate legacy companion-health training assets.

This script migrates legacy Neural Guard assets from the recovery folder into
the dedicated companion_health workspace and generates curation reports.
"""

import argparse
import csv
import hashlib
import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REQUIRED_COLUMNS = [
    "IsAnomaly",
    "TimeUS",
    "Type",
    "Volt",
    "Curr",
    "Roll",
    "Pitch",
    "Yaw",
    "C1",
    "C2",
    "C3",
    "C4",
    "VibeX",
    "VibeY",
    "VibeZ",
]

NUMERIC_COLUMNS = [
    "IsAnomaly",
    "TimeUS",
    "Volt",
    "Curr",
    "Roll",
    "Pitch",
    "Yaw",
    "C1",
    "C2",
    "C3",
    "C4",
    "VibeX",
    "VibeY",
    "VibeZ",
]

LEGACY_SCRIPT_NAMES = [
    "companion_monitor.py",
    "generate_training_data.py",
    "train_anomaly_model.py",
]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _to_float(value: str):
    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _load_rows(csv_path: Path):
    with csv_path.open(newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = list(reader.fieldnames or [])
    return fieldnames, rows


def _build_report(source_csv: Path, source_model: Path, rows: list, fieldnames: list) -> dict:
    type_counts = Counter()
    class_counts = Counter()
    invalid_numeric = Counter()
    empty_counts = Counter()
    numeric_min = {}
    numeric_max = {}

    dedupe_keys = set()
    duplicate_rows = 0

    for row in rows:
        row_key = tuple((k, row.get(k, "")) for k in fieldnames)
        if row_key in dedupe_keys:
            duplicate_rows += 1
        else:
            dedupe_keys.add(row_key)

        row_type = str(row.get("Type", "")).strip() or "UNKNOWN"
        type_counts[row_type] += 1

        anomaly_value = row.get("IsAnomaly", "")
        class_counts[str(anomaly_value).strip()] += 1

        for col in fieldnames:
            if str(row.get(col, "")).strip() == "":
                empty_counts[col] += 1

        for col in NUMERIC_COLUMNS:
            val = _to_float(row.get(col, ""))
            if val is None:
                if str(row.get(col, "")).strip() != "":
                    invalid_numeric[col] += 1
                continue

            if col not in numeric_min or val < numeric_min[col]:
                numeric_min[col] = val
            if col not in numeric_max or val > numeric_max[col]:
                numeric_max[col] = val

    row_count = len(rows)
    anomaly_rows = class_counts.get("1", 0)
    normal_rows = class_counts.get("0", 0)

    missing_columns = [c for c in REQUIRED_COLUMNS if c not in fieldnames]
    unknown_types = sorted([t for t in type_counts if t not in {"BAT", "ATT", "RCOU", "VIBE"}])

    curation_notes = []
    if row_count > 0:
        class_gap = abs(anomaly_rows - normal_rows)
        class_gap_pct = (class_gap / row_count) * 100.0
        if class_gap_pct <= 5.0:
            curation_notes.append("Class balance is near-even and usable for baseline anomaly training.")
        else:
            curation_notes.append("Class balance is skewed; consider class weighting during training.")

    if not missing_columns:
        curation_notes.append("Required telemetry schema is complete.")
    else:
        curation_notes.append("Schema mismatch detected; review missing required columns.")

    if duplicate_rows == 0:
        curation_notes.append("No full-row duplicates detected.")
    else:
        curation_notes.append("Duplicate rows found; de-duplication may improve training quality.")

    if unknown_types:
        curation_notes.append("Unknown message types found; inspect message taxonomy before training.")
    else:
        curation_notes.append("Message families are consistent with BAT/ATT/RCOU/VIBE capture.")

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": {
            "dataset": str(source_csv),
            "dataset_sha256": _sha256(source_csv),
            "model": str(source_model),
            "model_sha256": _sha256(source_model),
        },
        "summary": {
            "row_count": row_count,
            "column_count": len(fieldnames),
            "duplicate_rows": duplicate_rows,
            "class_distribution": {
                "normal": normal_rows,
                "anomaly": anomaly_rows,
                "other": row_count - (normal_rows + anomaly_rows),
            },
            "message_type_distribution": dict(sorted(type_counts.items())),
            "missing_required_columns": missing_columns,
            "unknown_message_types": unknown_types,
        },
        "data_quality": {
            "empty_cells_by_column": dict(sorted(empty_counts.items())),
            "invalid_numeric_values": dict(sorted(invalid_numeric.items())),
            "numeric_ranges": {
                col: {"min": numeric_min[col], "max": numeric_max[col]}
                for col in sorted(numeric_min.keys())
            },
        },
        "human_curation_notes": curation_notes,
        "review_actions": [
            "Keep this dataset as auxiliary anomaly-monitor data, not a replacement for BIN-level diagnosis labels.",
            "Re-train anomaly model when SITL scenario generation changes.",
            "Pair anomaly output with rule-based diagnosis to reduce false positives.",
        ],
    }

    return report


def _write_markdown_report(report: dict, report_md_path: Path) -> None:
    summary = report["summary"]
    quality = report["data_quality"]

    lines = [
        "# Companion Health Data Curation Report",
        "",
        "## Summary",
        f"- Rows: {summary['row_count']}",
        f"- Columns: {summary['column_count']}",
        f"- Duplicate rows: {summary['duplicate_rows']}",
        f"- Class distribution: {summary['class_distribution']}",
        f"- Message types: {summary['message_type_distribution']}",
        "",
        "## Data Quality",
        f"- Missing required columns: {summary['missing_required_columns'] or 'None'}",
        f"- Unknown message types: {summary['unknown_message_types'] or 'None'}",
        f"- Invalid numeric values: {quality['invalid_numeric_values'] or 'None'}",
        "",
        "## Human Curation Notes",
    ]

    for note in report["human_curation_notes"]:
        lines.append(f"- {note}")

    lines.extend(["", "## Review Actions"])
    for action in report["review_actions"]:
        lines.append(f"- {action}")

    report_md_path.write_text("\n".join(lines) + "\n")


def integrate(source_root: Path, output_root: Path) -> dict:
    source_csv = source_root / "training_dataset.csv"
    source_model = source_root / "anomaly_model.joblib"

    if not source_csv.exists():
        raise FileNotFoundError(f"Legacy dataset not found: {source_csv}")
    if not source_model.exists():
        raise FileNotFoundError(f"Legacy model not found: {source_model}")

    output_root.mkdir(parents=True, exist_ok=True)
    scripts_out = output_root / "legacy_scripts"
    scripts_out.mkdir(parents=True, exist_ok=True)

    copied_csv = output_root / "training_dataset.csv"
    copied_model = output_root / "anomaly_model.joblib"

    shutil.copy2(source_csv, copied_csv)
    shutil.copy2(source_model, copied_model)

    copied_scripts = []
    for script_name in LEGACY_SCRIPT_NAMES:
        src_script = source_root / script_name
        if src_script.exists():
            dst_script = scripts_out / script_name
            shutil.copy2(src_script, dst_script)
            copied_scripts.append(str(dst_script))

    fieldnames, rows = _load_rows(copied_csv)
    report = _build_report(source_csv, source_model, rows, fieldnames)
    report["output_root"] = str(output_root)
    report["destination"] = {
        "dataset": str(copied_csv),
        "model": str(copied_model),
    }
    report["copied_scripts"] = copied_scripts

    report_json_path = output_root / "dataset_report.json"
    report_md_path = output_root / "dataset_report.md"
    readme_path = output_root / "README.md"

    report_json_path.write_text(json.dumps(report, indent=2) + "\n")
    _write_markdown_report(report, report_md_path)

    readme_lines = [
        "# Companion Health Dataset",
        "",
        "This folder contains legacy Neural Guard assets migrated into the dedicated companion-health workspace.",
        "",
        "- `training_dataset.csv`: edge anomaly training data (row-level telemetry)",
        "- `anomaly_model.joblib`: legacy trained anomaly model",
        "- `legacy_scripts/`: original generation and training scripts",
        "- `dataset_report.json`: machine-readable validation report",
        "- `dataset_report.md`: human-readable curation summary",
        "",
        "This data is for companion-health anomaly workflows, separated from diagnosis benchmark labels.",
    ]
    readme_path.write_text("\n".join(readme_lines) + "\n")

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Integrate legacy companion-health data into dedicated folder")
    parser.add_argument(
        "--source-root",
        default="recovered_from_ardupilot_folder/legacy_neural_guard",
        help="Legacy Neural Guard folder",
    )
    parser.add_argument(
        "--output-root",
        default="companion_health/data/health_monitor",
        help="Destination folder for companion-health assets",
    )

    args = parser.parse_args()
    report = integrate(Path(args.source_root), Path(args.output_root))

    summary = report["summary"]
    print("Legacy companion-health assets integrated.")
    print(f"Rows: {summary['row_count']}")
    print(f"Class distribution: {summary['class_distribution']}")
    print(f"Message types: {summary['message_type_distribution']}")
    print(f"Report: {Path(args.output_root) / 'dataset_report.md'}")


if __name__ == "__main__":
    main()
