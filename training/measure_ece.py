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

import joblib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")          # headless
import matplotlib.pyplot as plt   # noqa: E402

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
    print(f"Reliability diagram saved → {output_path}")


def load_model_and_predict(features_csv: str, labels_csv: str):
    bundle = joblib.load("models/classifier.joblib")
    scaler = joblib.load("models/scaler.joblib")
    model = bundle["model"]
    classes = bundle["classes"]

    df_feat = pd.read_csv(features_csv)
    df_lab = pd.read_csv(labels_csv)

    X = df_feat.values
    class_names = []
    keep = []
    for i in range(len(df_lab)):
        row = df_lab.iloc[i]
        active = row[row == 1].index.tolist()
        if active and active[0] in classes:
            class_names.append(active[0])
            keep.append(i)

    if not keep:
        print("No labeled samples found matching known classes.")
        sys.exit(1)

    X = X[keep]
    y_true = np.array([classes.index(n) for n in class_names])
    X_scaled = scaler.transform(X)
    probs = model.predict_proba(X_scaled)
    return y_true, probs, classes


def main():
    parser = argparse.ArgumentParser(description="Measure ECE for the trained classifier")
    parser.add_argument("--features-csv", default="training/features.csv")
    parser.add_argument("--labels-csv", default="training/labels.csv")
    parser.add_argument(
        "--output-diagram",
        default="docs/reliability_diagram.png",
        help="Path to save reliability diagram PNG",
    )
    parser.add_argument(
        "--target-ece",
        type=float,
        default=ECE_PASS_THRESHOLD,
        help=f"ECE pass threshold (default {ECE_PASS_THRESHOLD})",
    )
    args = parser.parse_args()

    if not Path("models/classifier.joblib").exists():
        print("No trained model found. Run `python training/train_model.py` first.")
        sys.exit(1)

    print("Loading model and computing ECE...")
    y_true, probs, class_names = load_model_and_predict(
        args.features_csv, args.labels_csv
    )

    ece = compute_ece(y_true, probs)

    print(f"\n{'='*50}")
    print(f"  Overall ECE (macro): {ece:.4f}")
    print(f"  Target:              ≤ {args.target_ece:.2f}")
    if ece <= args.target_ece:
        print(f"  Result:              ✅ PASS")
    else:
        print(f"  Result:              ❌ FAIL — retraining or recalibration needed")
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
        flag = "✅" if class_ece <= args.target_ece else "⚠️ "
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
    report_path = "training/ece_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"ECE report saved → {report_path}")

    sys.exit(0 if ece <= args.target_ece else 1)


if __name__ == "__main__":
    main()
