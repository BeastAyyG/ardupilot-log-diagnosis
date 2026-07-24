"""
Train a Multi-Class classifier from feature/label CSVs.

Upgrades (v1.1.0):
- SMOTE oversampling with adaptive k_neighbors (handles tiny classes safely)
- CalibratedClassifierCV (sigmoid for small datasets, isotonic for large datasets)
- Expanded GridSearchCV param grid (depth, lr, estimators, scale_pos_weight)
- Saves calibration metadata to model bundle for audit trail

Usage: python -m training.train_model
"""

import argparse
import hashlib
import json
import os
import platform
import sys
import warnings
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

os.environ.setdefault(
    "LOKY_MAX_CPU_COUNT",
    os.environ.get("ARDUPILOT_TRAIN_JOBS", "4"),
)

import joblib
import numpy as np
import pandas as pd
import sklearn
import xgboost
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import precision_recall_fscore_support
from sklearn.model_selection import GridSearchCV, StratifiedKFold
from sklearn.preprocessing import LabelEncoder, StandardScaler
from xgboost import XGBClassifier

from src.constants import FEATURE_NAMES, VALID_LABELS
from training.dataset_integrity import (
    assert_group_isolation,
    stratified_group_holdout_indices,
)

warnings.filterwarnings("ignore", category=UserWarning)


def _configure_stdout() -> None:
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8", errors="replace")


def _safe_smote(X_train, y_train):
    """Apply SMOTE with adaptive k_neighbors — safe for tiny classes (n=2)."""
    from imblearn.over_sampling import SMOTE, RandomOverSampler

    _unique, counts = np.unique(y_train, return_counts=True)
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


def _locked_holdout_indices(
    groups: np.ndarray,
    y_str: np.ndarray,
    manifest_path: str,
) -> tuple[np.ndarray, np.ndarray]:
    with open(manifest_path, encoding="utf-8") as handle:
        manifest = json.load(handle)
    locked_ids = {
        str(item) for item in manifest.get("test_flight_ids", []) if str(item)
    }
    if not locked_ids:
        raise ValueError(
            f"Holdout manifest has no test_flight_ids: {manifest_path}"
        )

    available_ids = set(str(item) for item in groups)
    missing_ids = sorted(locked_ids - available_ids)
    if missing_ids:
        raise ValueError(
            "Locked holdout flights are missing from the current dataset: "
            + ", ".join(missing_ids[:5])
        )

    test_mask = np.isin(groups.astype(str), sorted(locked_ids))
    train_idx = np.flatnonzero(~test_mask)
    test_idx = np.flatnonzero(test_mask)
    missing_classes = sorted(set(y_str) - set(y_str[test_idx]))
    if missing_classes:
        raise ValueError(
            "Locked holdout does not represent every trained class: "
            + ", ".join(missing_classes)
        )
    return train_idx, test_idx


def train(holdout_manifest: str | None = None):
    _configure_stdout()
    features_csv = "training/features.csv"
    labels_csv = "training/labels.csv"
    model_dir = "models/"

    if not os.path.exists(features_csv) or not os.path.exists(labels_csv):
        print("Dataset CSVs not found. Run build_dataset.py first.")
        return

    df_feat = pd.read_csv(features_csv)
    df_lab = pd.read_csv(labels_csv)

    if len(df_feat) != len(df_lab):
        raise ValueError(
            "Feature/label row count mismatch: "
            f"{len(df_feat)} features vs {len(df_lab)} labels."
        )
    if "flight_id" not in df_feat.columns:
        raise ValueError(
            "training/features.csv must contain flight_id. Rebuild it with "
            "training/build_dataset.py to prevent source-flight leakage."
        )

    unknown_label_columns = sorted(set(df_lab.columns) - set(VALID_LABELS))
    if unknown_label_columns:
        raise ValueError(f"Unknown label columns: {unknown_label_columns}")

    # The historical TimeUS bug produced a second, identical full-flight row
    # for every source log. Remove only exact feature+label duplicates within
    # a flight so row duplication cannot inflate class support.
    integrity_frame = pd.concat(
        [df_feat.reset_index(drop=True), df_lab.reset_index(drop=True)],
        axis=1,
    )
    duplicate_mask = integrity_frame.duplicated(keep="first")
    duplicate_count = int(duplicate_mask.sum())
    if duplicate_count:
        print(f"Dropping {duplicate_count} exact duplicate training rows.")
        keep_mask = ~duplicate_mask
        df_feat = df_feat.loc[keep_mask].reset_index(drop=True)
        df_lab = df_lab.loc[keep_mask].reset_index(drop=True)

    label_signatures = df_lab.astype(int).astype(str).agg("".join, axis=1)
    signature_counts = (
        pd.DataFrame(
            {
                "flight_id": df_feat["flight_id"].astype(str),
                "label_signature": label_signatures,
            }
        )
        .groupby("flight_id")["label_signature"]
        .nunique()
    )
    conflicting_flights = signature_counts[signature_counts > 1].index.tolist()
    if conflicting_flights:
        raise ValueError(
            "Conflicting labels found within the same flight_id: "
            + ", ".join(conflicting_flights[:5])
        )

    groups = df_feat["flight_id"].astype(str).values
    df_feat = df_feat.drop(columns=["flight_id"])

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
    groups = groups[keep_indices]

    # Load rule-only labels to exclude them from ML model training
    rule_only_labels = []
    rule_only_path = os.path.join(os.path.dirname(features_csv), "rule_only_labels.json")
    if os.path.exists(rule_only_path):
        try:
            with open(rule_only_path, "r", encoding="utf-8") as f:
                rule_only_data = json.load(f)
                rule_only_labels = rule_only_data.get("rule_only_labels", [])
                print(f"Loaded rule-only labels to exclude from ML: {rule_only_labels}")
        except (OSError, TypeError, json.JSONDecodeError) as e:
            print(f"Error loading rule_only_labels.json: {e}")

    # Require enough distinct source flights for the five-fold grouped split.
    unique, counts = np.unique(y_str, return_counts=True)
    unique_group_counts = {
        class_name: len(set(groups[y_str == class_name]))
        for class_name in unique
    }
    print("\nClass distribution before filtering:")
    for cls, cnt in zip(unique, counts):
        if cls in rule_only_labels:
            flag = "✗ (excluded — rule-only label)"
        else:
            flag = (
                "✓"
                if unique_group_counts[cls] >= 5
                else "✗ (excluded — need ≥ 5 unique flights)"
            )
        print(
            f"  {cls:<25} rows={cnt:>4} "
            f"flights={unique_group_counts[cls]:>3}  {flag}"
        )

    valid_classes = [
        class_name
        for class_name in unique
        if unique_group_counts[class_name] >= 5
        and class_name not in rule_only_labels
    ]
    if len(valid_classes) < 2:
        raise ValueError(
            "At least two classes with five unique flights each are required "
            "for grouped training."
        )
    filter_mask = np.isin(y_str, valid_classes)
    X = X[filter_mask]
    y_str = y_str[filter_mask]
    groups = groups[filter_mask]

    # ── 2. Encode labels ────────────────────────────────────────────────────
    le = LabelEncoder()
    y = le.fit_transform(y_str)
    num_classes = len(le.classes_)
    print(f"\n{num_classes} classes retained: {le.classes_.tolist()}")

    # ── 3. Stratified group holdout ─────────────────────────────────────────
    # Selecting the first StratifiedGroupKFold fold omitted entire classes on
    # this small dataset. Allocate holdout flights per class explicitly.
    if holdout_manifest:
        train_idx, test_idx = _locked_holdout_indices(
            groups,
            y_str,
            holdout_manifest,
        )
        split_method = "locked_manifest"
    else:
        train_idx, test_idx = stratified_group_holdout_indices(
            y,
            groups,
            test_fraction=0.2,
            random_state=42,
        )
        split_method = "stratified_group_holdout"
    train_idx = np.asarray(train_idx, dtype=int)
    test_idx = np.asarray(test_idx, dtype=int)
    assert_group_isolation(groups, train_idx, test_idx)
    X_train, X_test = X[train_idx], X[test_idx]
    y_train, y_test = y[train_idx], y[test_idx]
    train_groups = [str(item) for item in sorted(set(groups[train_idx]))]
    test_groups = [str(item) for item in sorted(set(groups[test_idx]))]
    print(
        f"{split_method}: "
        f"train_groups={len(train_groups)}, test_groups={len(test_groups)}"
    )

    # Fit missing-value statistics on the training fold only. Computing
    # medians before the split would leak holdout distribution information.
    imputer = SimpleImputer(strategy="median", keep_empty_features=True)
    X_train_imputed = imputer.fit_transform(X_train)
    X_test_imputed = imputer.transform(X_test)

    # ── 4. SMOTE oversampling ───────────────────────────────────────────────
    print("\nApplying SMOTE to training split...")
    X_train_resampled, y_train_resampled = _safe_smote(
        X_train_imputed,
        y_train,
    )
    print(f"  Train size after SMOTE: {len(X_train_resampled)} (was {len(X_train)})")

    # ── 5. Feature scaling ──────────────────────────────────────────────────
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train_resampled)
    X_test_scaled = scaler.transform(X_test_imputed)

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
    training_jobs = int(os.environ.get("ARDUPILOT_TRAIN_JOBS", "4"))
    os.environ.setdefault("LOKY_MAX_CPU_COUNT", str(training_jobs))
    grid = GridSearchCV(
        xgb_base,
        param_grid,
        cv=cv,
        scoring="f1_macro",
        n_jobs=training_jobs,
        verbose=0,
    )
    grid.fit(X_train_scaled, y_train_resampled)
    xgb_clf = grid.best_estimator_
    print(f"  Best XGBoost params: {grid.best_params_}")

    # ── 8. Post-hoc calibration (ECE target ≤ 0.08) ─────────────────────────
    calibration_method = "sigmoid" if len(X_train) < 1_000 else "isotonic"
    print(f"\nApplying {calibration_method} probability calibration...")
    calibrated_clf = CalibratedClassifierCV(
        xgb_clf,
        method=calibration_method,
        cv=3,
    )
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
    cal_score, _ = evaluate(
        calibrated_clf,
        f"XGBoost + {calibration_method.title()} Calibration",
    )

    # ── 10. Save best model ─────────────────────────────────────────────────
    # The outer test fold is for reporting only. Selecting RF vs XGBoost using
    # this fold would leak evaluation information into the shipped artifact.
    best_model = calibrated_clf
    best_name = "XGBoost+Calibration"
    best_score = cal_score

    print(f"\nSaving {best_name} as final model (Macro F1={best_score:.3f})...")
    os.makedirs(model_dir, exist_ok=True)

    # ── 11. Train Anomaly Detector (Tier 2) on Healthy Logs ─────────────────
    print("\nTraining Tier 2 Anomaly Detector on 'healthy' logs...")
    # Use healthy samples from the training fold only. The outer test flights
    # remain completely unseen by every shipped artifact.
    if "healthy" in le.classes_:
        healthy_class = int(le.transform(["healthy"])[0])
        healthy_idx = np.flatnonzero(y_train == healthy_class)
    else:
        healthy_idx = np.array([], dtype=int)

    if len(healthy_idx) > 5:
        X_healthy = X_train_imputed[healthy_idx]
        # Train Isolation Forest on unscaled original healthy data, then scale it
        anomaly_scaler = StandardScaler()
        X_healthy_scaled = anomaly_scaler.fit_transform(X_healthy)

        iso_forest = IsolationForest(
            n_estimators=200,
            contamination=0.05,  # assume 5% of "healthy" data might actually be bad
            random_state=42,
        )
        iso_forest.fit(X_healthy_scaled)

        anomaly_bundle = {
            "iso_forest": iso_forest,
            "scaler": anomaly_scaler,
            "imputer": imputer,
            "sklearn_version": sklearn.__version__,
        }
        joblib.dump(anomaly_bundle, os.path.join(model_dir, "anomaly_detector.joblib"))
        print(f"  Anomaly Detector trained on {len(healthy_idx)} healthy samples and saved.")
    else:
        print(f"  Not enough healthy logs to train Anomaly Detector ({len(healthy_idx)} found, need > 5).")
        stale_anomaly_path = os.path.join(model_dir, "anomaly_detector.joblib")
        if os.path.exists(stale_anomaly_path):
            os.remove(stale_anomaly_path)
            print("  Removed stale anomaly detector artifact.")

    model_bundle = {
        "model": best_model,
        "classes": le.classes_.tolist(),
        "calibrated": isinstance(best_model, CalibratedClassifierCV),
        "calibration_method": (
            calibration_method
            if isinstance(best_model, CalibratedClassifierCV)
            else "none"
        ),
        "best_xgb_params": grid.best_params_,
        "macro_f1_test": best_score,
        "baseline_rf_macro_f1_test": rf_score,
        "uncalibrated_xgb_macro_f1_test": xgb_score,
        "num_classes": num_classes,
        "duplicate_rows_removed": duplicate_count,
        "train_flight_count": len(train_groups),
        "test_flight_count": len(test_groups),
        "test_flight_ids": test_groups,
        "split_method": split_method,
    }
    joblib.dump(model_bundle, os.path.join(model_dir, "classifier.joblib"))
    joblib.dump(imputer, os.path.join(model_dir, "imputer.joblib"))
    joblib.dump(scaler, os.path.join(model_dir, "scaler.joblib"))

    with open(os.path.join(model_dir, "feature_columns.json"), "w", encoding="utf-8") as f:
        json.dump(df_feat.columns.tolist(), f)
    with open(os.path.join(model_dir, "label_columns.json"), "w", encoding="utf-8") as f:
        json.dump(le.classes_.tolist(), f)

    threshold_path = os.path.join(model_dir, "rule_thresholds.yaml")
    threshold_hash = ""
    if os.path.exists(threshold_path):
        with open(threshold_path, "r", encoding="utf-8") as f:
            threshold_hash = hashlib.sha256(f.read().encode()).hexdigest()

    dataset_hasher = hashlib.sha256()
    for dataset_path in (features_csv, labels_csv):
        with open(dataset_path, "rb") as dataset_file:
            for chunk in iter(lambda: dataset_file.read(1024 * 1024), b""):
                dataset_hasher.update(chunk)

    manifest = {
        "model_version": best_name,
        "feature_schema_hash": hashlib.sha256(json.dumps(FEATURE_NAMES, sort_keys=True).encode()).hexdigest(),
        "label_schema_hash": hashlib.sha256(json.dumps(VALID_LABELS, sort_keys=True).encode()).hexdigest(),
        "training_dataset_id": dataset_hasher.hexdigest(),
        "eligible_flight_count": len(set(groups)),
        "training_flight_count": len(train_groups),
        "test_flight_count": len(test_groups),
        "test_flight_ids": test_groups,
        "split_method": split_method,
        "holdout_manifest_source": holdout_manifest or "",
        "duplicate_rows_removed": duplicate_count,
        "python_version": platform.python_version(),
        "sklearn_version": sklearn.__version__,
        "xgboost_version": xgboost.__version__,
        "calibration_method": calibration_method,
        "calibration_date": pd.Timestamp.now("UTC").strftime("%Y-%m-%d"),
        "threshold_config_hash": threshold_hash,
    }
    with open(os.path.join(model_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    # Evaluation report
    report_md = (
        f"# ML Evaluation Report\n\n"
        f"**Selected Model**: {best_name}\n"
        f"**Macro F1 Score**: {best_score:.3f}\n"
        f"**RandomForest Baseline Macro F1**: {rf_score:.3f}\n"
        f"**Uncalibrated XGBoost Macro F1**: {xgb_score:.3f}\n"
        f"**Calibration**: {calibration_method} (ECE target ≤ 0.08)\n"
        f"**Oversampling**: SMOTE (adaptive k_neighbors)\n"
        f"**Duplicate Rows Removed**: {duplicate_count}\n"
        f"**Train/Test Flight Groups**: {len(train_groups)}/{len(test_groups)}\n"
        f"**Best XGBoost Params**: {grid.best_params_}\n\n"
        f"Trained on {len(X_train_resampled)} balanced samples, "
        f"evaluated on {len(X_test)} unseen samples.\n"
    )
    with open("training/evaluation_report.md", "w", encoding="utf-8") as f:
        f.write(report_md)

    print("\nTraining complete. Artifacts saved to models/")
    print("Next: run `python training/measure_ece.py` to verify calibration quality.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train the grouped, calibrated ArduPilot classifier"
    )
    parser.add_argument(
        "--holdout-manifest",
        help=(
            "Optional previous model manifest whose test_flight_ids must remain "
            "locked for apples-to-apples evaluation."
        ),
    )
    args = parser.parse_args()
    train(holdout_manifest=args.holdout_manifest)


if __name__ == "__main__":
    main()
