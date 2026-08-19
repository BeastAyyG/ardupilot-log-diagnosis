"""
Train a Multi-Class classifier from feature/label CSVs.

Upgrades (v1.1.0):
- SMOTE oversampling with adaptive k_neighbors (handles tiny classes safely)
- CalibratedClassifierCV (isotonic) for ECE ≤ 0.08 target
- Expanded GridSearchCV param grid (depth, lr, estimators, scale_pos_weight)
- Saves calibration metadata to model bundle for audit trail

Usage: python training/train_model.py
"""

import argparse
import os
import sys
import json
import shutil

import hashlib
import warnings
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import numpy as np
import pandas as pd
import joblib
from src.constants import FEATURE_NAMES, VALID_LABELS
from sklearn.model_selection import GridSearchCV, StratifiedKFold
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier, IsolationForest
from sklearn.metrics import precision_recall_fscore_support
from xgboost import XGBClassifier
from lightgbm import LGBMClassifier
from sklearn.feature_selection import mutual_info_classif
from sklearn.ensemble import VotingClassifier, ExtraTreesClassifier
from training.evaluation_split import grouped_train_test_split
from training.data_contract import (
    ambiguous_group_labels,
    effective_group_values,
    primary_label_for_row,
)

warnings.filterwarnings("ignore", category=UserWarning)


def _configure_utf8_stdout() -> None:
    """Configure console output only for the standalone training command."""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass


def _validate_group_label_contract(
    labels: pd.DataFrame, groups: pd.DataFrame
) -> None:
    """Fail closed when one incident group has contradictory root causes."""

    ambiguous = ambiguous_group_labels(labels, groups, VALID_LABELS)
    if not ambiguous:
        return
    details = "; ".join(
        f"{group}: {', '.join(names)}"
        for group, names in sorted(ambiguous.items())
    )
    raise ValueError(
        "Ambiguous source groups contain multiple primary labels; "
        "add explicit incident_id/source_group metadata or exclude them: "
        + details
    )


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


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_window_contract(dataset_report_path: str) -> dict:
    default = {"version": 1, "window_sec": 5.0, "overlap": 0.5}
    if not os.path.exists(dataset_report_path):
        return {**default, "source": "training_default"}
    with open(dataset_report_path, "r", encoding="utf-8") as file_obj:
        report = json.load(file_obj)
    try:
        window_sec = float(report["window_sec"])
        overlap = float(report["overlap"])
        if window_sec <= 0 or not 0 <= overlap < 1:
            raise ValueError
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            "Dataset build report must contain valid window_sec and overlap values."
        ) from exc
    return {
        "version": 1,
        "window_sec": window_sec,
        "overlap": overlap,
        "include_full_log": True,
        "aggregation": "max_raw_probability",
        "source": "dataset_build_report",
    }


def _load_dataset_quality(dataset_report_path: str) -> dict:
    """Carry provenance/audit exclusions into the signed model manifest."""

    if not os.path.exists(dataset_report_path):
        return {}
    try:
        with open(dataset_report_path, "r", encoding="utf-8") as file_obj:
            report = json.load(file_obj)
    except (OSError, json.JSONDecodeError):
        return {}
    quality_keys = (
        "source_group_policy",
        "unique_source_groups",
        "skipped_duplicate_sha256",
        "skipped_ambiguous_group",
        "ambiguous_source_groups",
        "ambiguous_source_group_files",
        "excluded_ambiguous_groups",
        "excluded_ambiguous_rows",
    )
    return {key: report[key] for key in quality_keys if key in report}


def _validate_training_inputs(
    df_feat: pd.DataFrame, df_lab: pd.DataFrame, df_groups: pd.DataFrame
) -> None:
    if df_feat.columns.tolist() != FEATURE_NAMES:
        raise ValueError(
            "Feature schema mismatch: rebuild the dataset with the current FeaturePipeline before training."
        )
    if df_lab.columns.tolist() != VALID_LABELS:
        raise ValueError(
            "Label schema mismatch: labels CSV must preserve constants.VALID_LABELS order."
        )
    if "source_log" not in df_groups.columns:
        raise ValueError("Groups CSV must contain a 'source_log' column.")


def train(
    features_csv: str = "training/features.csv",
    labels_csv: str = "training/labels.csv",
    groups_csv: str = "training/groups.csv",
    model_dir: str = "models",
    dataset_report_path: str = "training/dataset_build_report.json",
    evaluation_report_path: str = "training/evaluation_report.md",
):

    if not os.path.exists(features_csv) or not os.path.exists(labels_csv) or not os.path.exists(groups_csv):
        print("Dataset CSVs or source-log groups not found. Run build_dataset.py first.")
        return

    df_feat = pd.read_csv(features_csv)
    df_lab = pd.read_csv(labels_csv)
    df_groups = pd.read_csv(groups_csv)
    if len(df_feat) != len(df_lab) or len(df_feat) != len(df_groups):
        raise ValueError("Features, labels, and groups CSVs must have the same row count.")
    _validate_training_inputs(df_feat, df_lab, df_groups)

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
    if not np.isfinite(df_feat.to_numpy(dtype=float)).all():
        raise ValueError("Feature CSV contains non-finite values after imputation.")

    window_contract = _load_window_contract(dataset_report_path)
    dataset_quality = _load_dataset_quality(dataset_report_path)

    # ── 1. Convert multi-label dummies → single root-cause string ──────────
    X = df_feat.values
    class_names = []
    keep_indices = []

    for i in range(len(df_lab)):
        row = df_lab.iloc[i]
        preferred = (
            df_groups.iloc[i].get("primary_label", "")
            if "primary_label" in df_groups.columns
            else ""
        )
        primary = primary_label_for_row(row, preferred=preferred, allowed=VALID_LABELS)
        if primary:
            class_names.append(primary)
            keep_indices.append(i)

    if not class_names:
        print("No valid labels found for any instances.")
        return

    X = X[keep_indices]
    y_str = np.array(class_names)
    groups = effective_group_values(df_groups)[keep_indices]

    # One source incident cannot have two contradictory single-target labels.
    # Require the dataset builder/provenance curator to provide distinct
    # incident_id/source_group values before fitting rather than choosing the
    # first attachment label and inflating or corrupting evaluation.
    _validate_group_label_contract(
        df_lab.iloc[keep_indices], df_groups.iloc[keep_indices]
    )

    # Require ≥ 2 samples per class for stratified split
    unique, counts = np.unique(y_str, return_counts=True)
    print("\nClass distribution before filtering:")
    for cls, cnt in zip(unique, counts):
        flag = "✓" if cnt >= 2 else "✗ (excluded — need ≥ 2 samples)"
        print(f"  {cls:<25} {cnt:>4}  {flag}")

    group_counts = {cls: len(set(groups[y_str == cls])) for cls in unique}
    for cls in unique:
        print(f"  independent source logs for {cls}: {group_counts[cls]}")
    valid_classes = np.array([cls for cls in unique if group_counts[cls] >= 2])
    filter_mask = np.isin(y_str, valid_classes)
    X = X[filter_mask]
    y_str = y_str[filter_mask]
    groups = groups[filter_mask]

    # ── 2. Encode labels ────────────────────────────────────────────────────
    le = LabelEncoder()
    y = le.fit_transform(y_str)
    num_classes = len(le.classes_)
    print(f"\n{num_classes} classes retained: {le.classes_.tolist()}")

    # ── 3. Stratified split ─────────────────────────────────────────────────
    train_indices, test_indices = grouped_train_test_split(y, groups)
    X_train, X_test = X[train_indices], X[test_indices]
    y_train, y_test = y[train_indices], y[test_indices]
    train_groups, test_groups = groups[train_indices], groups[test_indices]
    print(
        f"\nGrouped split: {len(set(train_groups))} source incidents train / "
        f"{len(set(test_groups))} source incidents test"
    )

    # ── 4. SMOTE oversampling ───────────────────────────────────────────────
    print("\nApplying SMOTE to training split...")
    X_train_resampled, y_train_resampled = _safe_smote(X_train, y_train)
    print(f"  Train size after SMOTE: {len(X_train_resampled)} (was {len(X_train)})")

    # ── 4.5. Feature selection (MI-based) ──────────────────────────────────
    n_available = X_train_resampled.shape[1]
    max_features = min(50, len(set(groups)) // 2, n_available)
    if max_features < n_available:
        print(f"\nFeature selection: {n_available} → top {max_features} by mutual information...")
        mi_scores = mutual_info_classif(
            X_train_resampled, y_train_resampled, random_state=42, n_neighbors=3
        )
        selected_mask = np.argsort(mi_scores)[-max_features:]
        selected_mask.sort()  # preserve column order
        X_train_resampled = X_train_resampled[:, selected_mask]
        X_test = X_test[:, selected_mask]
        X = X[:, selected_mask]  # for anomaly detector later
        selected_feature_names = [FEATURE_NAMES[i] for i in selected_mask]
        print(f"  Selected features: {selected_feature_names[:10]}... ({len(selected_feature_names)} total)")
    else:
        selected_mask = np.arange(n_available)
        selected_feature_names = FEATURE_NAMES[:]
        print(f"\nFeature selection: keeping all {n_available} features (groups too few to reduce)")

    # ── 5. Feature scaling ──────────────────────────────────────────────────
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train_resampled)
    X_test_scaled = scaler.transform(X_test)

    # ── 6. Baseline RandomForest ────────────────────────────────────────────
    print(f"\nTraining Baseline RandomForest ({num_classes} classes)...")
    rf_clf = RandomForestClassifier(
        n_estimators=300,
        max_depth=None,
        min_samples_leaf=2,
        class_weight="balanced_subsample",
        n_jobs=4,
        random_state=42,
    )
    rf_clf.fit(X_train_scaled, y_train_resampled)

    # ── 7. Tuned XGBoost (GridSearchCV) ────────────────────────────────────
    print("Training Tuned XGBoost (GridSearchCV)...")
    xgb_base = XGBClassifier(
        objective="multi:softprob",
        random_state=42,
        num_class=num_classes,
        eval_metric="mlogloss",
        n_jobs=1,
        verbosity=0,
    )
    # Keep the search bounded: the grouped corpus is much larger than the
    # original row-split dataset, so the old 216-combination grid was
    # impractical on a developer machine.
    param_grid = {
        "max_depth": [3, 5, 7],
        "learning_rate": [0.05, 0.1],
        "n_estimators": [100, 200, 300],
        "min_child_weight": [1, 3, 5],
        "subsample": [0.8, 1.0],
        "colsample_bytree": [0.8, 1.0],
        "scale_pos_weight": [1],
    }
    cv = StratifiedKFold(n_splits=3, shuffle=True, random_state=42)
    grid = GridSearchCV(
        xgb_base, param_grid, cv=cv, scoring="f1_macro", n_jobs=4, verbose=0
    )
    grid.fit(X_train_scaled, y_train_resampled)
    xgb_clf = grid.best_estimator_
    print(f"  Best XGBoost params: {grid.best_params_}")

    # ── 8. Isotonic calibration (ECE target ≤ 0.08) ─────────────────────────
    print("\nApplying isotonic probability calibration...")
    calibrated_clf = CalibratedClassifierCV(xgb_clf, method="isotonic", cv=3)
    calibrated_clf.fit(X_train_scaled, y_train_resampled)

    # ── 8.5. LightGBM candidate ─────────────────────────────────────────────
    print("\nTraining LightGBM candidate...")
    lgbm_clf = LGBMClassifier(
        objective="multiclass",
        num_class=num_classes,
        n_estimators=300,
        max_depth=5,
        learning_rate=0.05,
        num_leaves=31,
        min_child_samples=max(5, min(20, len(X_train_resampled) // num_classes // 5)),
        class_weight="balanced",
        random_state=42,
        verbose=-1,
        n_jobs=4,
    )
    lgbm_clf.fit(X_train_scaled, y_train_resampled)

    # ── 8.6. ExtraTrees candidate ───────────────────────────────────────────
    print("Training ExtraTrees candidate...")
    et_clf = ExtraTreesClassifier(
        n_estimators=300,
        max_depth=None,
        min_samples_leaf=2,
        class_weight="balanced_subsample",
        n_jobs=4,
        random_state=42,
    )
    et_clf.fit(X_train_scaled, y_train_resampled)

    # ── 8.7. Soft-voting ensemble ───────────────────────────────────────────
    print("Training soft-voting ensemble...")
    ensemble_clf = VotingClassifier(
        estimators=[
            ("rf", rf_clf),
            ("xgb", xgb_clf),
            ("lgbm", lgbm_clf),
            ("et", et_clf),
        ],
        voting="soft",
        n_jobs=1,  # inner models already parallel
    )
    # VotingClassifier with pre-fitted estimators
    ensemble_clf.estimators_ = [rf_clf, xgb_clf, lgbm_clf, et_clf]
    ensemble_clf.le_ = LabelEncoder().fit(np.arange(num_classes))
    ensemble_clf.classes_ = np.arange(num_classes)

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

    def evaluate_log_level(model, name):
        """Score one diagnosis per source log using max-over-window evidence."""
        probabilities = model.predict_proba(X_test_scaled)
        true_labels = []
        predicted_labels = []
        for source_log in np.unique(test_groups):
            indices = np.flatnonzero(test_groups == source_log)
            true_labels.append(int(y_test[indices[0]]))
            predicted_labels.append(int(np.max(probabilities[indices], axis=0).argmax()))
        _, _, f1, _ = precision_recall_fscore_support(
            true_labels,
            predicted_labels,
            zero_division=0,
            labels=np.arange(num_classes),
        )
        score = float(np.mean(f1))
        print(f"{name} log-level Macro F1 (max window evidence): {score:.3f}")
        return score

    rf_score, _ = evaluate(rf_clf, "RandomForest (baseline)")
    xgb_score, _ = evaluate(xgb_clf, "XGBoost (uncalibrated)")
    cal_score, _ = evaluate(calibrated_clf, "XGBoost + Isotonic Calibration")
    lgbm_score, _ = evaluate(lgbm_clf, "LightGBM")
    et_score, _ = evaluate(et_clf, "ExtraTrees")
    ens_score, _ = evaluate(ensemble_clf, "Ensemble (RF+XGB+LGBM+ET)")
    rf_log_score = evaluate_log_level(rf_clf, "RandomForest")
    xgb_log_score = evaluate_log_level(xgb_clf, "XGBoost (uncalibrated)")
    cal_log_score = evaluate_log_level(calibrated_clf, "XGBoost + Isotonic Calibration")
    lgbm_log_score = evaluate_log_level(lgbm_clf, "LightGBM")
    et_log_score = evaluate_log_level(et_clf, "ExtraTrees")
    ens_log_score = evaluate_log_level(ensemble_clf, "Ensemble")

    # ── 10. Save best model ─────────────────────────────────────────────────
    model_candidates = [
        (rf_log_score, rf_score, rf_clf, "RandomForest"),
        (xgb_log_score, xgb_score, xgb_clf, "XGBoost"),
        (cal_log_score, cal_score, calibrated_clf, "XGBoost+Calibration"),
        (lgbm_log_score, lgbm_score, lgbm_clf, "LightGBM"),
        (et_log_score, et_score, et_clf, "ExtraTrees"),
        (ens_log_score, ens_score, ensemble_clf, "Ensemble"),
    ]
    best_score, best_window_score, best_model, best_name = max(
        model_candidates, key=lambda item: item[0]
    )

    print(f"\nSaving {best_name} as final model (Macro F1={best_score:.3f})...")
    os.makedirs(model_dir, exist_ok=True)
    threshold_destination = os.path.join(model_dir, "rule_thresholds.yaml")
    threshold_source = Path("models") / "rule_thresholds.yaml"
    if not os.path.exists(threshold_destination) and threshold_source.exists():
        shutil.copy2(threshold_source, threshold_destination)

    # ── 11. Train Anomaly Detector (Tier 2) on Healthy Logs ─────────────────
    print("\nTraining Tier 2 Anomaly Detector on 'healthy' logs...")
    # We find all healthy samples in the original un-SMOTEd dataset
    healthy_idx = np.flatnonzero(y_str == "healthy").tolist()

    if len(healthy_idx) > 5:
        X_healthy = X[healthy_idx]
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
            "feature_columns": df_feat.columns.tolist(),
        }
        joblib.dump(anomaly_bundle, os.path.join(model_dir, "anomaly_detector.joblib"))
        with open(
            os.path.join(model_dir, "anomaly_feature_columns.json"), "w", encoding="utf-8"
        ) as file_obj:
            json.dump(df_feat.columns.tolist(), file_obj)
        print(f"  Anomaly Detector trained on {len(healthy_idx)} healthy samples and saved.")
    else:
        print(f"  Not enough healthy logs to train Anomaly Detector ({len(healthy_idx)} found, need > 5).")

    model_bundle = {
        "model": best_model,
        "classes": le.classes_.tolist(),
        "calibrated": isinstance(best_model, CalibratedClassifierCV),
        "calibration_method": "isotonic" if isinstance(best_model, CalibratedClassifierCV) else "none",
        "best_xgb_params": grid.best_params_,
        "macro_f1_test": best_score,
        "macro_f1_window_test": best_window_score,
        "macro_f1_log_test": best_score,
        "num_classes": num_classes,
        "inference_window": window_contract,
        "dataset_quality": dataset_quality,
    }
    joblib.dump(model_bundle, os.path.join(model_dir, "classifier.joblib"))
    joblib.dump(scaler, os.path.join(model_dir, "scaler.joblib"))

    model_feature_columns = selected_feature_names
    with open(os.path.join(model_dir, "feature_columns.json"), "w") as f:
        json.dump(model_feature_columns, f)
    with open(os.path.join(model_dir, "label_columns.json"), "w") as f:
        json.dump(le.classes_.tolist(), f)

    threshold_path = threshold_destination
    threshold_hash = ""
    if os.path.exists(threshold_path):
        with open(threshold_path, "r") as f:
            threshold_hash = hashlib.sha256(f.read().encode()).hexdigest()

    manifest = {
        "artifact_schema_version": 2,
        "model_version": best_name,
        "feature_schema_hash": hashlib.sha256(json.dumps(model_feature_columns, sort_keys=True).encode()).hexdigest(),
        "label_schema_hash": hashlib.sha256(json.dumps(le.classes_.tolist(), sort_keys=True).encode()).hexdigest(),
        "trained_label_schema_hash": hashlib.sha256(json.dumps(le.classes_.tolist(), sort_keys=True).encode()).hexdigest(),
        "runtime_label_schema_hash": hashlib.sha256(json.dumps(VALID_LABELS, sort_keys=True).encode()).hexdigest(),
        "training_dataset_id": f"{features_csv} + {labels_csv}",
        "training_inputs": {
            "features_sha256": _sha256_file(features_csv),
            "labels_sha256": _sha256_file(labels_csv),
            "groups_sha256": _sha256_file(groups_csv),
            "feature_row_count": len(df_feat),
            "label_row_count": len(df_lab),
            "source_log_count": int(len(set(groups))),
            "source_incident_group_count": int(len(set(groups))),
        },
        "evaluation": {
            "macro_f1_log_test": float(best_score),
            "macro_f1_window_test": float(best_window_score),
            "test_source_log_count": int(len(set(test_groups))),
            "train_source_log_count": int(len(set(train_groups))),
            "test_source_incident_group_count": int(len(set(test_groups))),
            "train_source_incident_group_count": int(len(set(train_groups))),
        },
        "inference_window": window_contract,
        "dataset_quality": dataset_quality,
        "calibration_date": pd.Timestamp.now("UTC").strftime("%Y-%m-%d"),
        "threshold_config_hash": threshold_hash,
        "feature_selection": {
            "method": "mutual_information",
            "original_count": len(FEATURE_NAMES),
            "selected_count": len(selected_feature_names),
            "selected_features": selected_feature_names,
        },
    }
    with open(os.path.join(model_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    # Evaluation report
    report_md = (
        f"# ML Evaluation Report\n\n"
        f"**Selected Model**: {best_name}  \n"
        f"**Log-level Macro F1 Score (max window evidence)**: {best_score:.3f}  \n"
        f"**Window-level Macro F1 Score**: {best_window_score:.3f}  \n"
        f"**Calibration**: {'isotonic' if isinstance(best_model, CalibratedClassifierCV) else 'none'} (ECE target <= 0.08)  \n"
        f"**Oversampling**: SMOTE (adaptive k_neighbors)  \n"
        f"**Best XGBoost Params**: {grid.best_params_}  \n\n"
        f"Trained on {len(X_train_resampled)} balanced samples, "
        f"evaluated on {len(X_test)} samples from {len(set(test_groups))} unseen source incidents.\n\n"
        f"**Training feature count**: {len(model_feature_columns)}  \n"
        f"**ML-supported labels**: {', '.join(le.classes_.tolist())}  \n"
        f"**Rules-only labels**: {', '.join(sorted(set(VALID_LABELS) - set(le.classes_.tolist()))) or 'none'}  \n"
        f"**Inference window contract**: {window_contract['window_sec']}s / {window_contract['overlap']} overlap + full log\n"
    )
    report_parent = os.path.dirname(evaluation_report_path)
    if report_parent:
        os.makedirs(report_parent, exist_ok=True)
    with open(evaluation_report_path, "w", encoding="utf-8") as f:
        f.write(report_md)

    print(f"\nTraining complete. Artifacts saved to {model_dir}")
    print("Next: run `python training/measure_ece.py` to verify calibration quality.")


if __name__ == "__main__":
    _configure_utf8_stdout()
    parser = argparse.ArgumentParser(description="Train a grouped ArduPilot diagnosis model.")
    parser.add_argument("--features-csv", default="training/features.csv")
    parser.add_argument("--labels-csv", default="training/labels.csv")
    parser.add_argument("--groups-csv", default="training/groups.csv")
    parser.add_argument("--model-dir", default="models")
    parser.add_argument("--dataset-report", default="training/dataset_build_report.json")
    parser.add_argument("--evaluation-report", default="training/evaluation_report.md")
    cli_args = parser.parse_args()
    train(
        features_csv=cli_args.features_csv,
        labels_csv=cli_args.labels_csv,
        groups_csv=cli_args.groups_csv,
        model_dir=cli_args.model_dir,
        dataset_report_path=cli_args.dataset_report,
        evaluation_report_path=cli_args.evaluation_report,
    )
