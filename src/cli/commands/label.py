from __future__ import annotations

import json
import os
from argparse import _SubParsersAction

from src.diagnosis.hybrid_engine import HybridEngine

from .common import load_features


def register(subparsers: _SubParsersAction) -> None:
    parser = subparsers.add_parser("label", help="Interactive labeling tool")
    parser.add_argument("logfile", help="Path to .BIN file")
    parser.set_defaults(func=run)


def run(args) -> None:
    logfile = args.logfile
    filename = os.path.basename(logfile)
    features = load_features(logfile)

    engine = HybridEngine()
    diagnoses = engine.diagnose(features)

    print(f"\n--- Labeling {filename} ---")
    auto_labels = features.get("_metadata", {}).get("auto_labels", [])
    if auto_labels:
        print(f"Auto-suggested labels from ERR/EV: {auto_labels}")

    print("\nModel Predictions:")
    if diagnoses:
        for diagnosis in diagnoses:
            print(f" - {diagnosis['failure_type']} ({int(diagnosis['confidence'] * 100)}%)")
    else:
        print(" - None (Healthy)")

    print("\nEnter correct labels (comma-separated). Uses constants.VALID_LABELS.")
    print("Leave blank to skip.")
    try:
        user_input = input("Labels > ").strip()
    except EOFError:
        user_input = ""

    if not user_input:
        print("Skipped.")
        return

    labels = [label.strip() for label in user_input.split(",")]
    gt_path = "ground_truth.json"
    data = {"logs": []}
    if os.path.exists(gt_path):
        with open(gt_path, "r") as file_obj:
            data = json.load(file_obj)

    data["logs"] = [entry for entry in data.get("logs", []) if entry["filename"] != filename]
    data["logs"].append(
        {
            "filename": filename,
            "labels": labels,
            "source_url": "",
            "source_type": "manual",
            "expert_quote": "",
            "confidence": "high",
        }
    )

    with open(gt_path, "w") as file_obj:
        json.dump(data, file_obj, indent=2)
    print(f"Added {filename} to {gt_path} with labels {labels}")
