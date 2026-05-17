from __future__ import annotations

import csv
import fnmatch
import logging
import os
from argparse import _SubParsersAction
from pathlib import Path
from tqdm import tqdm

from src.parser.bin_parser import LogParser
from src.features.pipeline import FeaturePipeline
from src.diagnosis.hybrid_engine import HybridEngine
from src.diagnosis.decision_policy import evaluate_decision

logger = logging.getLogger(__name__)


def register(subparsers: _SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "batch",
        help="Batch analyze a directory of .BIN logs recursively",
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory containing .BIN files to scan (default: current directory)",
    )
    parser.add_argument(
        "--output",
        "-o",
        required=True,
        help="Path to save the output CSV summary",
    )
    parser.add_argument(
        "--include",
        nargs="*",
        default=[],
        metavar="PATTERN",
        help=(
            "Only process files whose names match at least one of these glob "
            "patterns (e.g. '*.BIN' 'flight_*'). When omitted all .BIN files "
            "are included."
        ),
    )
    parser.add_argument(
        "--exclude",
        nargs="*",
        default=[],
        metavar="PATTERN",
        help=(
            "Skip files whose names match any of these glob patterns "
            "(e.g. 'test_*' 'tmp_*'). Applied after --include filtering."
        ),
    )
    parser.set_defaults(func=run)


def run(args) -> None:
    directory = args.directory
    output_path = args.output

    if not os.path.exists(directory):
        print(f"Directory {directory} not found.")
        return

    include_patterns = getattr(args, "include", []) or []
    exclude_patterns = getattr(args, "exclude", []) or []

    # Recursively scan for .BIN files (case-insensitive), applying glob filters
    bin_files = []
    for root, _, files in os.walk(directory):
        for file in files:
            if not file.upper().endswith(".BIN"):
                continue
            # --include: must match at least one pattern (skip check when list is empty)
            if include_patterns and not any(
                fnmatch.fnmatch(file, pat) for pat in include_patterns
            ):
                continue
            # --exclude: skip if matches any pattern
            if exclude_patterns and any(
                fnmatch.fnmatch(file, pat) for pat in exclude_patterns
            ):
                continue
            bin_files.append(Path(root) / file)

    # Sort files to ensure deterministic processing order
    bin_files.sort()

    if not bin_files:
        print("No .BIN files found")
        return

    pipeline = FeaturePipeline()
    engine = HybridEngine()

    # Open CSV for writing and stream rows directly to keep memory usage low
    with open(output_path, "w", newline="", encoding="utf-8") as csv_file:
        fieldnames = [
            "filename",
            "duration",
            "vehicle",
            "diagnosis",
            "confidence",
            "requires_review",
        ]
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()

        for filepath in tqdm(bin_files, desc="Analyzing logs"):
            # Compute relative path to the scanned directory
            rel_path = os.path.relpath(str(filepath), start=str(directory))
            # Normalize path to use forward slashes (standard cross-platform representation)
            rel_path = rel_path.replace("\\", "/")

            try:
                # 1. Parse the file
                parser = LogParser(str(filepath))
                parsed = parser.parse()

                # 2. Extract features
                features = pipeline.extract(parsed)
                metadata = features.get("_metadata", {})

                # 3. Check extraction success
                if not metadata.get("extraction_success", True):
                    raise ValueError("Extraction failed: empty or corrupt log")

                # 4. Diagnose
                diagnoses = engine.diagnose(features)

                # 5. Evaluate decision
                decision = evaluate_decision(diagnoses)

                # 6. Extract fields
                duration = float(metadata.get("duration_sec", 0.0))
                vehicle = metadata.get("vehicle_type", "Unknown")

                if diagnoses:
                    top_diag = diagnoses[0]
                    diagnosis = top_diag["failure_type"]
                    confidence = float(top_diag["confidence"])
                else:
                    diagnosis = "healthy"
                    confidence = 0.0

                requires_review = bool(decision.get("requires_human_review", False))

                # 7. Stream row to CSV
                writer.writerow({
                    "filename": rel_path,
                    "duration": duration,
                    "vehicle": vehicle,
                    "diagnosis": diagnosis,
                    "confidence": confidence,
                    "requires_review": requires_review,
                })
                csv_file.flush()

            except Exception as exc:
                logger.warning(f"Failed to analyze {rel_path}: {exc}")
