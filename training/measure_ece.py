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
from itertools import pairwise
from pathlib import Path

import joblib
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")          # headless
import matplotlib.pyplot as plt

ECE_PASS_THRESHOLD = 0.08


def _configure_stdout() -> None:
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8", errors="replace")


def compute_ece(y_true: np.ndarray, probs: np.ndarray, n_bins: int = 10) -> float:
    """Compute standard top-label Expected Calibration Error."""
    if len(y_true) == 0:
        raise ValueError("ECE requires at least one evaluation sample")

    predicted = np.argmax(probs, axis=1)
    confidence = np.max(probs, axis=1)
    correct = (predicted == y_true).astype(float)
    bins = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    for index, (lo, hi) in enumerate(pairwise(bins)):
        upper = confidence <= hi if index == n_bins - 1 else confidence < hi
        mask = (confidence >= lo) & upper
        if mask.sum() == 0:
            continue
        ece += (mask.sum() / len(y_true)) * abs(
            confidence[mask].mean() - correct[mask].mean()
        )
    return float(ece)


def reliability_diagram(y_true, probs, class_names, output_path):
    """Save a reliability diagram for each class."""
    n_classes = probs.shape[1]
    n_bins = 10
    bins = np.linspace(0, 1, n_bins + 1)
    cols = min(4, n_classes)
    rows = (n_classes + cols - 1) // cols

    _fig, axes = plt.subplots(rows, cols, figsize=(4 * cols, 4 * rows))
    axes = np.array(axes).flatten()

    for c, ax in zip(range(n_classes), axes):
        p = probs[:, c]
        label = (y_true == c).astype(int)
        conf_vals, acc_vals = [], []
        for index, (lo, hi) in enumerate(pairwise(bins)):
            upper = p <= hi if index == n_bins - 1 else p < hi
            mask = (p >= lo) & upper
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


def load_model_and_predict(
    features_csv: str,
    labels_csv: str,
    evaluation_scope: str = "saved-holdout",
):
    bundle = joblib.load("models/classifier.joblib")
    imputer = joblib.load("models/imputer.joblib")
    scaler = joblib.load("models/scaler.joblib")
    manifest = json.loads(Path("models/manifest.json").read_text(encoding="utf-8"))
    model = bundle["model"]
    classes = bundle["classes"]

    df_feat = pd.read_csv(features_csv)
    df_lab = pd.read_csv(labels_csv)

    if "flight_id" not in df_feat.columns:
        raise ValueError("ECE evaluation requires flight_id in the feature CSV")
    flight_ids = df_feat["flight_id"].astype(str)

    if evaluation_scope == "saved-holdout":
        holdout_ids = set(manifest.get("test_flight_ids", []))
        if not holdout_ids:
            raise ValueError(
                "Model manifest has no saved grouped holdout. Retrain before "
                "claiming an ECE score."
            )
        scope_mask = flight_ids.isin(holdout_ids)
        if not scope_mask.any():
            raise ValueError(
                "None of the model's saved holdout flights are present in the "
                "provided feature CSV."
            )
        df_feat = df_feat.loc[scope_mask].reset_index(drop=True)
        df_lab = df_lab.loc[scope_mask].reset_index(drop=True)
        flight_ids = flight_ids.loc[scope_mask].reset_index(drop=True)

    df_feat = df_feat.drop(columns=["flight_id"])
    df_feat = df_feat.replace([np.inf, -np.inf], np.nan)

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
    evaluated_flight_ids = flight_ids.iloc[keep].astype(str).tolist()
    y_true = np.array([classes.index(n) for n in class_names])
    X_imputed = imputer.transform(X)
    X_scaled = scaler.transform(X_imputed)
    probs = model.predict_proba(X_scaled)
    return y_true, probs, classes, evaluated_flight_ids


def main():
    _configure_stdout()
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
    parser.add_argument(
        "--evaluation-scope",
        choices=["saved-holdout", "all-provided"],
        default="saved-holdout",
        help=(
            "Evaluate the grouped holdout saved by training (default), or all "
            "rows in a separately supplied external dataset."
        ),
    )
    args = parser.parse_args()

    if not Path("models/classifier.joblib").exists():
        print("No trained model found. Run `python training/train_model.py` first.")
        sys.exit(1)

    print("Loading model and computing ECE...")
    y_true, probs, class_names, evaluated_flight_ids = load_model_and_predict(
        args.features_csv,
        args.labels_csv,
        evaluation_scope=args.evaluation_scope,
    )

    ece = compute_ece(y_true, probs)

    print(f"\n{'='*50}")
    print(f"  Overall ECE (top-label): {ece:.4f}")
    print(f"  Target:              ≤ {args.target_ece:.2f}")
    if ece <= args.target_ece:
        print("  Result:              ✅ PASS")
    else:
        print("  Result:              ❌ FAIL — retraining or recalibration needed")
    print(f"{'='*50}\n")

    # Per-class ECE breakdown
    print("Per-class ECE:")
    n_bins = 10
    bins = np.linspace(0, 1, n_bins + 1)
    for c, name in enumerate(class_names):
        p = probs[:, c]
        label = (y_true == c).astype(int)
        class_ece = 0.0
        for index, (lo, hi) in enumerate(pairwise(bins)):
            upper = p <= hi if index == n_bins - 1 else p < hi
            mask = (p >= lo) & upper
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
        "evaluation_scope": args.evaluation_scope,
        "evaluated_flight_ids": evaluated_flight_ids,
    }
    report_path = "training/ece_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"ECE report saved → {report_path}")

    sys.exit(0 if ece <= args.target_ece else 1)


if __name__ == "__main__":
    main()
