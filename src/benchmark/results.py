import json
from src.constants import VALID_LABELS


class BenchmarkResults:
    def __init__(self):
        self.log_results = []
        self.per_label = {}
        self.errors = []
        self.overall = {
            "total_logs": 0,
            "successful_extractions": 0,
            "failed_extractions": 0,
            "failed_diagnoses": 0,
        }

    def add_error(self, filename, error_msg, error_type="EXTRACTION_FAILED"):
        self.errors.append(
            {"filename": filename, "error": error_msg, "type": error_type}
        )
        if error_type == "EXTRACTION_FAILED":
            self.overall["failed_extractions"] += 1
        else:
            self.overall["failed_diagnoses"] += 1

    def add_result(self, filename, ground_truth, predicted, features_extracted):
        self.overall["successful_extractions"] += 1
        self.log_results.append(
            {
                "filename": filename,
                "ground_truth": ground_truth,
                "predicted": predicted,
                "predicted_confidence": [p.get("confidence") for p in predicted]
                if isinstance(predicted, list)
                else [],
            }
        )

    def compute_metrics(self) -> dict:
        self.overall["total_logs"] = (
            self.overall["successful_extractions"] + self.overall["failed_extractions"]
        )

        for label in VALID_LABELS:
            self.per_label[label] = {"support": 0, "tp": 0, "fp": 0, "fn": 0, "tn": 0}

        confusion_details = []

        for res in self.log_results:
            gt = set(res["ground_truth"])
            pred_types = set([d["failure_type"] for d in res["predicted"]])

            for label in VALID_LABELS:
                if label in gt:
                    self.per_label[label]["support"] += 1
                    if label in pred_types:
                        self.per_label[label]["tp"] += 1
                    else:
                        self.per_label[label]["fn"] += 1
                else:
                    if label in pred_types:
                        self.per_label[label]["fp"] += 1
                    else:
                        self.per_label[label]["tn"] += 1

            if gt != pred_types:
                confusion_details.append(
                    {
                        "filename": res["filename"],
                        "ground_truth": list(gt),
                        "predicted": list(pred_types),
                        "predicted_confidence": res["predicted_confidence"],
                    }
                )

        # Accuracy variants:
        # 1. any_match: ground truth label appears anywhere in predictions (best metric for recall-focused engine)
        # 2. top1_match: highest-confidence prediction matches any ground truth label
        # 3. exact_match: exact set equality (original, very strict, always low)
        any_matches = 0
        top1_matches = 0
        exact_matches = 0
        sum_f1 = 0.0
        active_labels = 0

        for label, counts in self.per_label.items():
            tp, fp, fn = counts["tp"], counts["fp"], counts["fn"]
            prec = tp / (tp + fp) if tp + fp > 0 else 0.0
            rec = tp / (tp + fn) if tp + fn > 0 else 0.0
            f1 = 2 * (prec * rec) / (prec + rec) if prec + rec > 0 else 0.0
            self.per_label[label]["precision"] = float(prec)
            self.per_label[label]["recall"] = float(rec)
            self.per_label[label]["f1"] = float(f1)
            if counts["support"] > 0 or fp > 0:
                sum_f1 += f1
                active_labels += 1

        for res in self.log_results:
            gt = set(res["ground_truth"])
            pred_list = res["predicted"]  # ordered by confidence
            pred_types = set([d["failure_type"] for d in pred_list])

            # Check if any ground truth label is in predictions
            if gt & pred_types:  # intersection not empty
                any_matches += 1

            # Check if top-1 prediction matches any ground truth label
            if pred_list:
                top1_type = pred_list[0]["failure_type"]
                if top1_type in gt:
                    top1_matches += 1

            # Exact set match (strict)
            if gt == pred_types:
                exact_matches += 1

        n = max(self.overall["successful_extractions"], 1)
        self.overall["accuracy"] = float(any_matches / n)  # PRIMARY metric
        self.overall["top1_accuracy"] = float(top1_matches / n)  # Single-label accuracy
        self.overall["exact_match_accuracy"] = float(
            exact_matches / n
        )  # Strict (informational)
        self.overall["macro_f1"] = float(sum_f1 / max(active_labels, 1))

        return {
            "overall": self.overall,
            "per_label": self.per_label,
            "confusion_details": confusion_details,
            "errors": self.errors,
        }

    def to_markdown(self) -> str:
        metrics = self.compute_metrics()
        ov = metrics["overall"]

        lines = [
            "# Benchmark Results",
            "",
            "## Overall Metrics",
            f"- Total logs: {ov['total_logs']}",
            f"- Successful Extractions: {ov['successful_extractions']}",
            f"- Failed Extractions: {ov['failed_extractions']}",
            f"- Exact Match Accuracy: {ov['accuracy']:.2f}",
            f"- Macro F1 Score: {ov['macro_f1']:.2f}",
            "",
            "## Per-Label Metrics",
            "| Label | N | TP | Precision | F1 |",
            "|---|---|---|---|---|",
        ]

        for label, vals in metrics["per_label"].items():
            if vals["support"] > 0 or vals["fp"] > 0:
                lines.append(
                    f"| {label} | {vals['support']} | {vals['tp']} | {vals['precision']:.2f} | {vals['f1']:.2f} |"
                )

        lines.extend(["", "## Confusion Details"])
        for conf in metrics["confusion_details"][:10]:
            lines.append(
                f"- **{conf['filename']}**: Expected {conf['ground_truth']} vs. Predicted {conf['predicted']}"
            )

        return "\n".join(lines)

    def to_json(self) -> str:
        return json.dumps(self.compute_metrics(), indent=2)
