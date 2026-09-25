import json
import os
import sys
from pathlib import Path

# Fix python path
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.features.pipeline import FeaturePipeline
from src.parser.bin_parser import LogParser
from src.diagnosis.rule_engine import RuleEngine


def relabel():
    gt_path = "data/holdouts/production_holdout_clean/ground_truth.json"
    dataset_dir = "data/holdouts/production_holdout_clean/dataset"
    # Suggestions are written beside the ground truth for human review. The
    # rule engine must never overwrite labels it is later evaluated against
    # (CORRECTIONS.md, C8).
    out_path = "data/holdouts/production_holdout_clean/ground_truth.rule_suggestions.json"

    with open(gt_path, "r") as f:
        data = json.load(f)

    pipeline = FeaturePipeline()
    rules = RuleEngine()

    relabeled_count = 0
    suggestions = []
    SYMPTOM_LABELS = {
        "mechanical_failure",
        "rc_failsafe",
        "ekf_failure",
        "crash_unknown",
    }
    PHYSICAL_ROOT_CAUSES = {
        "vibration_high",
        "compass_interference",
        "power_instability",
    }

    for i, log_entry in enumerate(data.get("logs", [])):
        original_labels = set(log_entry.get("labels", []))

        # Check if the labes are considered "Symptom" labels
        is_symptom = any(label in SYMPTOM_LABELS for label in original_labels)

        if is_symptom or len(original_labels) == 0:
            filepath = os.path.join(dataset_dir, log_entry["filename"])
            if not os.path.exists(filepath):
                continue

            parser = LogParser(filepath)
            parsed = parser.parse()
            if not parsed.get("messages"):
                continue

            features = pipeline.extract(parsed)
            rule_diagnoses = rules.diagnose(features)

            # Find the strongest physical root cause
            strongest_cause = None
            max_conf = 0.0

            for diag in rule_diagnoses:
                if (
                    diag["failure_type"] in PHYSICAL_ROOT_CAUSES
                    and diag["confidence"] > 0.65
                ):
                    if diag["confidence"] > max_conf:
                        max_conf = diag["confidence"]
                        strongest_cause = diag["failure_type"]

            if strongest_cause:
                print(f"Rule suggestion for Holdout {log_entry['filename']}")
                print(f"  Label: {list(original_labels)}")
                print(f"  Rule suggests: {strongest_cause} (Confidence: {max_conf:.2f})")
                suggestions.append(
                    {
                        "filename": log_entry["filename"],
                        "labels": sorted(original_labels),
                        "rule_suggestion": strongest_cause,
                        "rule_confidence": round(max_conf, 4),
                        "status": "needs_human_review",
                    }
                )
                relabeled_count += 1

    with open(out_path, "w") as f:
        json.dump({"source": gt_path, "suggestions": suggestions}, f, indent=2)

    print(f"\nWrote {relabeled_count} rule suggestions (labels unchanged) for holdout logs.")


if __name__ == "__main__":
    relabel()
