from __future__ import annotations

import csv
import os
from argparse import _SubParsersAction
from pathlib import Path

from src.cli.formatter import DiagnosisFormatter
from src.diagnosis.decision_policy import evaluate_decision
from src.diagnosis.hybrid_engine import HybridEngine
from src.diagnosis.rule_engine import RuleEngine
from src.features.pipeline import FeaturePipeline
from src.parser.bin_parser import LogParser


def register(subparsers: _SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "batch-analyze",
        aliases=["batch"],
        help="Batch analyze a directory of .BIN logs — writes CSV summary + per-log JSON",
    )
    parser.add_argument("directory", help="Directory containing .BIN files")
    parser.add_argument("--output-dir", "-o", default=None, help="Directory for per-log JSON reports and batch_summary.csv")
    parser.add_argument("--engine", choices=["rule", "hybrid"], default="hybrid", help="Diagnosis engine to use (default: hybrid)")
    parser.set_defaults(func=run)


def run(args) -> None:
    directory = args.directory
    if not os.path.exists(directory):
        print(f"Directory {directory} not found.")
        return

    output_dir = args.output_dir
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    pipeline = FeaturePipeline()
    engine = HybridEngine() if getattr(args, "engine", "hybrid") != "rule" else RuleEngine()

    bin_files = sorted(filename for filename in os.listdir(directory) if filename.upper().endswith(".BIN"))
    if not bin_files:
        print(f"No .BIN files found in {directory}")
        if output_dir:
            csv_path = os.path.join(output_dir, "batch_summary.csv")
            fieldnames = ["filename", "status", "top_diagnosis", "confidence", "severity", "requires_review"]
            with open(csv_path, "w", newline="") as csv_file:
                csv.DictWriter(csv_file, fieldnames=fieldnames).writeheader()
            print(f"Summary CSV  -> {csv_path} (header only — no logs found)")
        return

    formatter = DiagnosisFormatter()
    rows = []
    healthy = fail = error = 0

    col_w = max(len(filename) for filename in bin_files) + 2
    header = f"{'File':<{col_w}} | {'Status':<9} | {'Top Diagnosis':<30} | Conf"
    print(header)
    print("-" * len(header))

    for filename in bin_files:
        filepath = os.path.join(directory, filename)
        try:
            parsed = LogParser(filepath).parse()
            features = pipeline.extract(parsed)
            metadata = features.get("_metadata", {})
            if not metadata.get("extraction_success", True):
                raise ValueError("Extraction failed: empty or corrupt log")

            diagnoses = engine.diagnose(features)
            decision = evaluate_decision(diagnoses)

            if not diagnoses:
                status = "HEALTHY"
                top_label = "-"
                conf = 0.0
                severity = "-"
                healthy += 1
            else:
                top = diagnoses[0]
                top_label = top["failure_type"]
                conf = top["confidence"]
                severity = top["severity"]
                status = "CRITICAL" if severity == "critical" else "WARNING"
                fail += 1

            rows.append(
                {
                    "filename": filename,
                    "status": status,
                    "top_diagnosis": top_label,
                    "confidence": f"{conf:.2f}",
                    "severity": severity,
                    "requires_review": decision.get("requires_human_review", False),
                }
            )
            conf_str = f"{conf:.0%}" if conf > 0 else "-"
            print(f"{filename:<{col_w}} | {status:<9} | {top_label:<30} | {conf_str}")

            if output_dir:
                stem = Path(filename).stem
                report_json = formatter.format_json(diagnoses, metadata, features, decision=decision)
                json_path = os.path.join(output_dir, f"{stem}_report.json")
                with open(json_path, "w") as json_file:
                    json_file.write(report_json)
        except Exception as exc:
            error += 1
            rows.append({"filename": filename, "status": "ERROR", "error": str(exc)})
            print(f"{filename:<{col_w}} | {'ERROR':<9} | {str(exc)[:30]:<30} | -")

    print(f"\nSummary: {healthy} healthy · {fail} issues · {error} errors · {len(bin_files)} total")

    incident_rows = [row for row in rows if row.get("status") not in ("ERROR", "HEALTHY")]
    if incident_rows:
        clusters: dict[str, list[str]] = {}
        for row in incident_rows:
            label = row.get("top_diagnosis", "unknown")
            clusters.setdefault(label, []).append(row["filename"])
        print("\nDuplicate Incident Clusters:")
        for label, files in sorted(clusters.items(), key=lambda item: -len(item[1])):
            print(f"  [{len(files):>2}x] {label}")
            for filename in files:
                print(f"         · {filename}")

    if output_dir:
        csv_path = os.path.join(output_dir, "batch_summary.csv")
        fieldnames = ["filename", "status", "top_diagnosis", "confidence", "severity", "requires_review"]
        with open(csv_path, "w", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            if rows:
                writer.writerows(rows)
        if rows:
            print(f"Summary CSV  -> {csv_path}")
            print(f"JSON reports -> {output_dir}/*.json")
        else:
            print(f"Summary CSV  -> {csv_path} (header only — no logs processed)")
