#!/usr/bin/env python3
"""
auto_label_candidates.py

Scans a directory of raw, unlabeled .BIN files, runs the rules engine
over them, and flags any logs where starved/rule-only class rules fire
with high confidence (>= 0.6).

Output is written to a provisional labels JSON, ready for expert review.
"""

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.parser.bin_parser import LogParser
from src.features.pipeline import FeaturePipeline
from src.diagnosis.rule_engine import RuleEngine

# Starved classes we want to graduate from rule-only to ML-classifiable
TARGET_CLASSES = {
    "pid_tuning_issue",
    "power_instability",
    "motor_imbalance",
    "mechanical_failure",
    "thrust_loss",
    "setup_error"
}

SHA_PREFIX_RE = re.compile(r"^([0-9a-fA-F]{10,64})__")


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def auto_label_directory(
    target_dir: str,
    ground_truth_path: str,
    output_provisional_path: str,
    min_confidence: float = 0.60
) -> None:
    print(f"Scanning target directory: {target_dir}")
    print(f"Loading ground truth to skip already-labeled logs: {ground_truth_path}")

    # 1. Load existing ground truth filenames
    labeled_filenames = set()
    labeled_hash_prefixes = set()
    if os.path.exists(ground_truth_path):
        try:
            with open(ground_truth_path, "r", encoding="utf-8") as f:
                gt_data = json.load(f)
                for log in gt_data.get("logs", []):
                    filename = log.get("filename")
                    if filename:
                        labeled_filenames.add(filename)
                        match = SHA_PREFIX_RE.match(filename)
                        if match:
                            labeled_hash_prefixes.add(match.group(1).lower())
                    for key in ("sha256", "sha256_prefix"):
                        value = str(log.get(key, "")).strip().lower()
                        if len(value) >= 10:
                            labeled_hash_prefixes.add(value)
            print(f"Loaded {len(labeled_filenames)} already-labeled logs from ground truth.")
            print(
                f"Loaded {len(labeled_hash_prefixes)} labeled SHA prefixes "
                "for content deduplication."
            )
        except Exception as e:
            print(f"Warning: Could not read ground truth file: {e}")

    # 2. Find all unlabeled .BIN/bin files in target directory
    unlabeled_files = []
    for root, _, files in os.walk(target_dir):
        for file in files:
            if file.lower().endswith(".bin") and file not in labeled_filenames:
                unlabeled_files.append(os.path.join(root, file))

    print(f"Found {len(unlabeled_files)} unlabeled .bin files.")
    if not unlabeled_files:
        print("No unlabeled files to process.")
        return

    # 3. Process logs
    pipeline = FeaturePipeline()
    rule_engine = RuleEngine()
    provisional_logs = []

    success_count = 0
    candidate_count = 0
    duplicate_content_count = 0
    seen_hashes = set()

    for idx, filepath in enumerate(unlabeled_files):
        filename = os.path.basename(filepath)
        print(f"[{idx+1}/{len(unlabeled_files)}] Processing {filename}...")

        try:
            sha256 = _sha256(filepath)
            if sha256 in seen_hashes or any(
                sha256.startswith(prefix) for prefix in labeled_hash_prefixes
            ):
                duplicate_content_count += 1
                print(
                    f"  Skipping {filename}: duplicate of labeled/seen content "
                    f"(SHA256 {sha256[:12]}...)."
                )
                continue
            seen_hashes.add(sha256)

            parser = LogParser(filepath)
            try:
                parsed = parser.parse()
            except Exception as pe:
                print(f"  Skipping {filename}: pymavlink parse error: {pe}")
                continue

            if not parsed:
                print(f"  Skipping {filename}: empty or parse failed.")
                continue

            features = pipeline.extract(parsed)
            rule_results = rule_engine.diagnose(features)
            success_count += 1

            # Check if any rule results match target classes with confidence >= min_confidence
            matched_diag = None
            for diag in rule_results:
                ftype = diag.get("failure_type")
                conf = diag.get("confidence", 0.0)
                if ftype in TARGET_CLASSES and conf >= min_confidence:
                    if matched_diag is None or conf > matched_diag.get("confidence", 0.0):
                        matched_diag = diag

            if matched_diag:
                candidate_count += 1
                evidence_strs = [
                    f"{ev['feature']}={ev['value']} (threshold: {ev['threshold']})"
                    for ev in matched_diag.get("evidence", [])
                ]
                print(f"  FOUND candidate: {matched_diag['failure_type']} (conf: {matched_diag['confidence']:.2f})")

                provisional_logs.append({
                    "filename": filename,
                    "path": os.path.abspath(filepath),
                    "sha256": sha256,
                    "size_mb": round(os.path.getsize(filepath) / (1024 * 1024), 2),
                    "status": "auto_labeled_high_confidence" if matched_diag["confidence"] >= 0.75 else "auto_labeled_low_confidence",
                    "auto_label": matched_diag["failure_type"],
                    "confidence": matched_diag["confidence"],
                    "engine": "rule",
                    "evidence": evidence_strs,
                    "rule_top": matched_diag["failure_type"],
                    "rule_conf": matched_diag["confidence"],
                    "human_verified": False,
                    "notes": "Auto-flagged as candidate by rule engine"
                })

        except Exception as e:
            print(f"  Error processing {filename}: {e}")

    # 4. Save provisional auto-labels
    if provisional_logs:
        os.makedirs(os.path.dirname(output_provisional_path), exist_ok=True)
        output_data = {
            "description": "Provisional auto-labels for starved failures awaiting human verification.",
            "total_logs": len(provisional_logs),
            "logs": provisional_logs
        }
        with open(output_provisional_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2)
        print(f"\nSaved {len(provisional_logs)} candidates to {output_provisional_path}")
    else:
        print("\nNo candidates matching starved classes found.")
    print(f"Skipped duplicate content: {duplicate_content_count}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Auto-label candidate flight logs using rules engine")
    parser.add_argument(
        "--target-dir",
        default="data/kaggle_backups",
        help="Directory containing unlabeled .BIN logs"
    )
    parser.add_argument(
        "--ground-truth",
        default="data/combined_dataset/ground_truth.json",
        help="Path to combined ground truth JSON"
    )
    parser.add_argument(
        "--output",
        default="data/to_label/provisional_auto_labels_next.json",
        help="Path to save provisional auto-labels"
    )
    parser.add_argument(
        "--min-conf",
        type=float,
        default=0.60,
        help="Minimum confidence threshold for flagging candidates"
    )
    args = parser.parse_args()

    auto_label_directory(
        target_dir=args.target_dir,
        ground_truth_path=args.ground_truth,
        output_provisional_path=args.output,
        min_confidence=args.min_conf
    )
