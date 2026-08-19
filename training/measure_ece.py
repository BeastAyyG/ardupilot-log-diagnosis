"""
Measure Expected Calibration Error (ECE) of the trained classifier.

ECE quantifies whether confidence scores are statistically trustworthy:
  - ECE = 0.05 means "when the model says 70%, it's actually right ~65-75% of the time"
  - ECE > 0.15 means confidence outputs cannot be trusted by maintainers

Target: ECE ≤ 0.08 (production gate).

Usage:
    python training/measure_ece.py
    python training/measure_ece.py --dataset-dir data/holdouts/... --ground-truth ...
"""

import argparse
import json
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import joblib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")          # headless
import matplotlib.pyplot as plt   # noqa: E402
from training.evaluation_split import grouped_train_test_split
from training.data_contract import effective_group_values, primary_label_for_row

ECE_PASS_THRESHOLD = 0.08


def compute_ece(y_true: np.ndarray, probs: np.ndarray, n_bins: int = 10) -> float:
    """Compute scalar ECE across all classes (macro average)."""
    n_classes = probs.shape[1]
    ece_per_class = []

    for c in range(n_classes):
        p = probs[:, c]
        label = (y_true == c).astype(int)
        bins = np.linspace(0, 1, n_bins + 1)
        bin_ece = 0.0
        for lo, hi in zip(bins[:-1], bins[1:]):
            mask = (p >= lo) & (p < hi)
            if mask.sum() == 0:
                continue
            avg_conf = p[mask].mean()
            avg_acc = label[mask].mean()
            bin_ece += mask.sum() * abs(avg_conf - avg_acc)
        ece_per_class.append(bin_ece / len(y_true))

    return float(np.mean(ece_per_class))


def aggregate_group_probabilities(
    y_true: np.ndarray, probs: np.ndarray, groups: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Apply the deployed max-window contract before measuring calibration.

    The runtime reports one diagnosis per source incident using the maximum
    raw class probability across its windows (including the full-log window).
    Measuring ECE on every correlated window would overweight long flights and
    certify a confidence behaviour the deployed service does not expose.
    """

    y_true = np.asarray(y_true)
    probs = np.asarray(probs, dtype=float)
    groups = np.asarray(groups)
    if len(y_true) != len(probs) or len(y_true) != len(groups):
        raise ValueError("ECE arrays must have the same row count.")
    if len(y_true) == 0:
        return y_true, probs

    grouped_true = []
    grouped_probs = []
    for group in np.unique(groups):
        indices = np.flatnonzero(groups == group)
        grouped_true.append(y_true[indices[0]])
        grouped_probs.append(np.max(probs[indices], axis=0))
    return np.asarray(grouped_true), np.asarray(grouped_probs)


def reliability_diagram(y_true, probs, class_names, output_path):
    """Save a reliability diagram for each class."""
    n_classes = probs.shape[1]
    n_bins = 10
    bins = np.linspace(0, 1, n_bins + 1)
    cols = min(4, n_classes)
    rows = (n_classes + cols - 1) // cols

    fig, axes = plt.subplots(rows, cols, figsize=(4 * cols, 4 * rows))
    axes = np.array(axes).flatten()

    for c, ax in zip(range(n_classes), axes):
        p = probs[:, c]
        label = (y_true == c).astype(int)
        conf_vals, acc_vals = [], []
        for lo, hi in zip(bins[:-1], bins[1:]):
            mask = (p >= lo) & (p < hi)
            if mask.sum() == 0:
                continue
            conf_vals.append(p[mask].mean())
            acc_vals.append(label[mask].mean())

        ax.plot([0, 1], [0, 1], "k--", lw=1, label="Perfect")
        if conf_vals:
            ax.plot(conf_vals, acc_vals, "b-o", ms=4, label="Model")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.set_title(class_names[c], fontsize=9)
        ax.set_xlabel("Confidence", fontsize=7)
        ax.set_ylabel("Accuracy", fontsize=7)
        ax.legend(fontsize=7)

    for ax in axes[n_classes:]:
        ax.set_visible(False)

    plt.suptitle("Reliability Diagram — ArduPilot Classifier", fontsize=12)
    plt.tight_layout()
    plt.savefig(output_path, dpi=120)
    plt.close()
    print(f"Reliability diagram saved to {output_path}")


def load_model_and_predict(
    features_csv: str, labels_csv: str, groups_csv: str, model_dir: str = "models"
):
    model_root = Path(model_dir)
    bundle = joblib.load(model_root / "classifier.joblib")
    scaler = joblib.load(model_root / "scaler.joblib")
    model = bundle["model"]
    classes = bundle["classes"]

    # The runtime dataset may contain newer rule-only features than the
    # deployed model. Evaluate the exact ordered model columns.
    feature_schema_path = model_root / "feature_columns.json"
    model_feature_columns = json.loads(feature_schema_path.read_text(encoding="utf-8"))

    df_feat = pd.read_csv(features_csv)
    df_lab = pd.read_csv(labels_csv)
    df_groups = pd.read_csv(groups_csv)
    if len(df_feat) != len(df_lab) or len(df_feat) != len(df_groups):
        raise ValueError("Features, labels, and groups CSVs must have the same row count.")

    missing = [name for name in model_feature_columns if name not in df_feat.columns]
    if missing:
        raise ValueError("Dataset is missing model feature columns: " + ", ".join(missing))
    X = df_feat.loc[:, model_feature_columns].to_numpy()
    class_names = []
    keep = []
    for i in range(len(df_lab)):
        row = df_lab.iloc[i]
        preferred = (
            df_groups.iloc[i].get("primary_label", "")
            if "primary_label" in df_groups.columns
            else ""
        )
        primary = primary_label_for_row(row, preferred=preferred, allowed=classes)
        if primary:
            class_names.append(primary)
            keep.append(i)

    if not keep:
        print("No labeled samples found matching known classes.")
        sys.exit(1)

    X = X[keep]
    y_true = np.array([classes.index(n) for n in class_names])
    groups = effective_group_values(df_groups)[keep]
    _, test_indices = grouped_train_test_split(y_true, groups)
    X_scaled = scaler.transform(X[test_indices])
    y_true = y_true[test_indices]
    groups = groups[test_indices]
    probs = model.predict_proba(X_scaled)
    cal_file = model_root / "calibration_params.json"
    if cal_file.exists():
        try:
            cal_params = json.loads(cal_file.read_text(encoding="utf-8"))
            if cal_params.get("method") == "temperature" and "temperature" in cal_params:
                T = cal_params["temperature"]
                logits = np.log(probs + 1e-12) / T
                exp_logits = np.exp(logits - np.max(logits, axis=1, keepdims=True))
                probs = exp_logits / exp_logits.sum(axis=1, keepdims=True)
                print(f"Applied Temperature Scaling (T={T:.4f})")
        except Exception:
            pass

    y_true, probs = aggregate_group_probabilities(y_true, probs, groups)
    return y_true, probs, classes


def main():
    parser = argparse.ArgumentParser(description="Measure ECE for the trained classifier")
    parser.add_argument("--features-csv", default="training/features.csv")
    parser.add_argument("--labels-csv", default="training/labels.csv")
    parser.add_argument("--groups-csv", default="training/groups.csv")
    parser.add_argument("--model-dir", default="models")
    parser.add_argument(
        "--output-diagram",
        default="docs/reliability_diagram.png",
        help="Path to save reliability diagram PNG",
    )
    parser.add_argument(
        "--report-path",
        default="training/ece_report.json",
        help="Path for the machine-readable ECE report",
    )
    parser.add_argument(
        "--target-ece",
        type=float,
        default=ECE_PASS_THRESHOLD,
        help=f"ECE pass threshold (default {ECE_PASS_THRESHOLD})",
    )
    args = parser.parse_args()

    if not (Path(args.model_dir) / "classifier.joblib").exists():
        print("No trained model found. Run `python training/train_model.py` first.")
        sys.exit(1)

    print("Loading model and computing ECE...")
    y_true, probs, class_names = load_model_and_predict(
        args.features_csv, args.labels_csv, args.groups_csv, args.model_dir
    )

    ece = compute_ece(y_true, probs)

    print(f"\n{'='*50}")
    print(f"  Overall ECE (macro): {ece:.4f}")
    print(f"  Target:              <= {args.target_ece:.2f}")
    if ece <= args.target_ece:
        print("  Result:              PASS")
    else:
        print("  Result:              FAIL - retraining or recalibration needed")
    print(f"{'='*50}\n")

    # Per-class ECE breakdown
    print("Per-class ECE:")
    n_bins = 10
    bins = np.linspace(0, 1, n_bins + 1)
    for c, name in enumerate(class_names):
        p = probs[:, c]
        label = (y_true == c).astype(int)
        class_ece = 0.0
        for lo, hi in zip(bins[:-1], bins[1:]):
            mask = (p >= lo) & (p < hi)
            if mask.sum() == 0:
                continue
            class_ece += mask.sum() * abs(p[mask].mean() - label[mask].mean())
        class_ece /= len(y_true)
        flag = "PASS" if class_ece <= args.target_ece else "WARN"
        print(f"  {flag} {name:<25} ECE={class_ece:.4f}")

    # Reliability diagram
    os.makedirs(os.path.dirname(args.output_diagram), exist_ok=True)
    reliability_diagram(y_true, probs, class_names, args.output_diagram)

    # Write JSON report
    report = {
        "overall_ece": ece,
        "target_ece": args.target_ece,
        "pass": ece <= args.target_ece,
        "n_samples": len(y_true),
        "classes": class_names,
    }
    report_parent = Path(args.report_path).parent
    if str(report_parent):
        report_parent.mkdir(parents=True, exist_ok=True)
    with open(args.report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"ECE report saved to {args.report_path}")

    sys.exit(0 if ece <= args.target_ece else 1)


if __name__ == "__main__":
    main()
