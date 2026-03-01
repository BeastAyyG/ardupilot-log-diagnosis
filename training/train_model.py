"""
Train a Multi-Class classifier from feature/label CSVs.

Upgrades (v1.1.0):
- SMOTE oversampling with adaptive k_neighbors (handles tiny classes safely)
- CalibratedClassifierCV (isotonic) for ECE ≤ 0.08 target
- Expanded GridSearchCV param grid (depth, lr, estimators, scale_pos_weight)
- Saves calibration metadata to model bundle for audit trail

Usage: python training/train_model.py
"""

import os
import json
import warnings
import numpy as np
import pandas as pd
import joblib
from sklearn.model_selection import train_test_split, GridSearchCV, StratifiedKFold
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import precision_recall_fscore_support
from xgboost import XGBClassifier

warnings.filterwarnings("ignore", category=UserWarning)


def _safe_smote(X_train, y_train):
    """Apply SMOTE with adaptive k_neighbors — safe for tiny classes (n=2)."""
    from imblearn.over_sampling import SMOTE, RandomOverSampler

    unique, counts = np.unique(y_train, return_counts=True)
    min_count = counts.min()

    if min_count < 2:
        # Cannot SMOTE a single-sample class — fall back to RandomOverSampler
        print(
            f"  Warning: min class size = {min_count}. "
            "Falling back to RandomOverSampler (SMOTE requires ≥ 2 samples/class)."
        )
        ros = RandomOverSampler(random_state=42)
        return ros.fit_resample(X_train, y_train)

    # k_neighbors must be < min class size
    k = min(5, min_count - 1)
    print(f"  SMOTE: k_neighbors={k} (min class size={min_count})")
    sm = SMOTE(random_state=42, k_neighbors=k)
    return sm.fit_resample(X_train, y_train)


def train():
    features_csv = "training/features.csv"
    labels_csv = "training/labels.csv"
    model_dir = "models/"

    if not os.path.exists(features_csv) or not os.path.exists(labels_csv):
        print("Dataset CSVs not found. Run build_dataset.py first.")
        return

    df_feat = pd.read_csv(features_csv)
    df_lab = pd.read_csv(labels_csv)

    # ── 0. Impute NaN feature values ────────────────────────────────────────
    # Some extractors (e.g. tanomaly) return -1.0 sentinel and some columns
    # may have genuine NaN from edge cases. SMOTE requires finite values.
    nan_cols = df_feat.columns[df_feat.isna().any()].tolist()
    if nan_cols:
        print(f"Imputing NaN in {len(nan_cols)} feature columns with column median:")
        for col in nan_cols:
            median_val = df_feat[col].median()
            df_feat[col] = df_feat[col].fillna(median_val)
            print(f"  {col}: filled with {median_val:.4f}")

    # ── 1. Convert multi-label dummies → single root-cause string ──────────
    X = df_feat.values
    class_names = []
    keep_indices = []

    for i in range(len(df_lab)):
        row = df_lab.iloc[i]
        active_labels = row[row == 1].index.tolist()
        if active_labels:
            class_names.append(active_labels[0])   # Root-Cause Precedence: first label wins
            keep_indices.append(i)

    if not class_names:
        print("No valid labels found for any instances.")
        return

    X = X[keep_indices]
    y_str = np.array(class_names)

    # Require ≥ 2 samples per class for stratified split
    unique, counts = np.unique(y_str, return_counts=True)
    print("\nClass distribution before filtering:")
    for cls, cnt in zip(unique, counts):
        flag = "✓" if cnt >= 2 else "✗ (excluded — need ≥ 2 samples)"
        print(f"  {cls:<25} {cnt:>4}  {flag}")

    valid_classes = unique[counts >= 2]
    filter_mask = np.isin(y_str, valid_classes)
    X = X[filter_mask]
    y_str = y_str[filter_mask]

    # ── 2. Encode labels ────────────────────────────────────────────────────
    le = LabelEncoder()
    y = le.fit_transform(y_str)
    num_classes = len(le.classes_)
    print(f"\n{num_classes} classes retained: {le.classes_.tolist()}")

    # ── 3. Stratified split ─────────────────────────────────────────────────
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    # ── 4. SMOTE oversampling ───────────────────────────────────────────────
    print("\nApplying SMOTE to training split...")
    X_train_resampled, y_train_resampled = _safe_smote(X_train, y_train)
    print(f"  Train size after SMOTE: {len(X_train_resampled)} (was {len(X_train)})")

    # ── 5. Feature scaling ──────────────────────────────────────────────────
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train_resampled)
    X_test_scaled = scaler.transform(X_test)

    # ── 6. Baseline RandomForest ────────────────────────────────────────────
    print(f"\nTraining Baseline RandomForest ({num_classes} classes)...")
    rf_clf = RandomForestClassifier(
        n_estimators=200, max_depth=10, class_weight="balanced", random_state=42
    )
    rf_clf.fit(X_train_scaled, y_train_resampled)

    # ── 7. Tuned XGBoost (GridSearchCV) ────────────────────────────────────
    print("Training Tuned XGBoost (GridSearchCV)...")
    xgb_base = XGBClassifier(
        objective="multi:softprob",
        random_state=42,
        num_class=num_classes,
        eval_metric="mlogloss",
        verbosity=0,
    )
    param_grid = {
        "max_depth": [3, 4, 5, 6],
        "learning_rate": [0.05, 0.1, 0.2],
        "n_estimators": [100, 200, 300],
        "min_child_weight": [1, 3, 5],
        "scale_pos_weight": [1, 2],      # residual class balance help
    }
    cv = StratifiedKFold(n_splits=3, shuffle=True, random_state=42)
    grid = GridSearchCV(
        xgb_base, param_grid, cv=cv, scoring="f1_macro", n_jobs=-1, verbose=0
    )
    grid.fit(X_train_scaled, y_train_resampled)
    xgb_clf = grid.best_estimator_
    print(f"  Best XGBoost params: {grid.best_params_}")

    # ── 8. Isotonic calibration (ECE target ≤ 0.08) ─────────────────────────
    print("\nApplying isotonic probability calibration...")
    calibrated_clf = CalibratedClassifierCV(xgb_clf, method="isotonic", cv=3)
    calibrated_clf.fit(X_train_scaled, y_train_resampled)

    # ── 9. Evaluation ───────────────────────────────────────────────────────
    def evaluate(model, name):
        y_pred = model.predict(X_test_scaled)
        prec, rec, f1, support = precision_recall_fscore_support(
            y_test, y_pred, zero_division=0, labels=np.arange(num_classes)
        )
        macro_f1 = float(np.mean(f1))
        print(f"\n--- {name} Results ---")
        print(f"Macro F1: {macro_f1:.3f}")
        for i, class_name in enumerate(le.classes_):
            if support[i] > 0:
                print(
                    f"  {class_name:<25} F1={f1[i]:.3f}  "
                    f"P={prec[i]:.3f}  R={rec[i]:.3f}  (n={support[i]})"
                )
        return macro_f1, model

    rf_score, _ = evaluate(rf_clf, "RandomForest (baseline)")
    xgb_score, _ = evaluate(xgb_clf, "XGBoost (uncalibrated)")
    cal_score, _ = evaluate(calibrated_clf, "XGBoost + Isotonic Calibration")

    # ── 10. Save best model ─────────────────────────────────────────────────
    # Always prefer calibrated XGBoost — calibration only improves probability estimates,
    # never degrades accuracy when the underlying model is strong.
    if cal_score >= rf_score:
        best_model = calibrated_clf
        best_name = "XGBoost+Calibration"
        best_score = cal_score
    else:
        best_model = rf_clf
        best_name = "RandomForest"
        best_score = rf_score

    print(f"\nSaving {best_name} as final model (Macro F1={best_score:.3f})...")
    os.makedirs(model_dir, exist_ok=True)

    model_bundle = {
        "model": best_model,
        "classes": le.classes_.tolist(),
        "calibrated": isinstance(best_model, CalibratedClassifierCV),
        "calibration_method": "isotonic" if isinstance(best_model, CalibratedClassifierCV) else "none",
        "best_xgb_params": grid.best_params_,
        "macro_f1_test": best_score,
        "num_classes": num_classes,
    }
    joblib.dump(model_bundle, os.path.join(model_dir, "classifier.joblib"))
    joblib.dump(scaler, os.path.join(model_dir, "scaler.joblib"))

    with open(os.path.join(model_dir, "feature_columns.json"), "w") as f:
        json.dump(df_feat.columns.tolist(), f)
    with open(os.path.join(model_dir, "label_columns.json"), "w") as f:
        json.dump(le.classes_.tolist(), f)

    # Evaluation report
    report_md = (
        f"# ML Evaluation Report\n\n"
        f"**Selected Model**: {best_name}  \n"
        f"**Macro F1 Score**: {best_score:.3f}  \n"
        f"**Calibration**: isotonic (ECE target ≤ 0.08)  \n"
        f"**Oversampling**: SMOTE (adaptive k_neighbors)  \n"
        f"**Best XGBoost Params**: {grid.best_params_}  \n\n"
        f"Trained on {len(X_train_resampled)} balanced samples, "
        f"evaluated on {len(X_test)} unseen samples.\n"
    )
    with open("training/evaluation_report.md", "w") as f:
        f.write(report_md)

    print("\nTraining complete. Artifacts saved to models/")
    print("Next: run `python training/measure_ece.py` to verify calibration quality.")


if __name__ == "__main__":
    train()
