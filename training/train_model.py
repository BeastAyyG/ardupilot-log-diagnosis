"""
Train a Multi-Class classifier from feature/label CSVs using Over-Sampling.
Usage: python training/train_model.py
"""

import os
import json
import numpy as np
import pandas as pd
import joblib
from sklearn.model_selection import train_test_split, GridSearchCV
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import precision_recall_fscore_support
from xgboost import XGBClassifier
from imblearn.over_sampling import RandomOverSampler


def train():
    features_csv = "training/features.csv"
    labels_csv = "training/labels.csv"
    model_dir = "models/"

    if not os.path.exists(features_csv) or not os.path.exists(labels_csv):
        print("Dataset CSVs not found. Run build_dataset.py first.")
        return

    df_feat = pd.read_csv(features_csv)
    df_lab = pd.read_csv(labels_csv)

    # 1. Convert Multi-Label dummy variables to Single Root-Cause string
    X = df_feat.values

    # Pick the first label that has a '1' for each row
    class_names = []
    keep_indices = []

    for i in range(len(df_lab)):
        row = df_lab.iloc[i]
        active_labels = row[row == 1].index.tolist()
        if active_labels:
            class_names.append(active_labels[0])
            keep_indices.append(i)

    if not class_names:
        print("No valid labels found for any instances.")
        return

    X = X[keep_indices]
    y_str = np.array(class_names)

    # Require at least 2 samples per class for StratifiedSplit
    unique, counts = np.unique(y_str, return_counts=True)
    valid_classes = unique[counts >= 2]

    filter_mask = np.isin(y_str, valid_classes)
    X = X[filter_mask]
    y_str = y_str[filter_mask]

    # 2. Encode to integers
    le = LabelEncoder()
    y = le.fit_transform(y_str)
    num_classes = len(le.classes_)

    # 3. Stratified Split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    # 4. Oversampling to fix extreme imbalance
    ros = RandomOverSampler(random_state=42)
    X_train_resampled, y_train_resampled = ros.fit_resample(X_train, y_train)

    # 5. Scaling
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train_resampled)
    X_test_scaled = scaler.transform(X_test)

    print(f"Training Baseline RandomForest (Multi-Class on {num_classes} classes)...")
    rf_clf = RandomForestClassifier(
        n_estimators=100, max_depth=10, class_weight="balanced", random_state=42
    )
    rf_clf.fit(X_train_scaled, y_train_resampled)

    print("Training Tuned XGBoost (GridSearchCV)...")
    xgb = XGBClassifier(
        objective="multi:softprob", random_state=42, num_class=num_classes
    )
    param_grid = {
        "max_depth": [3, 5, 7],
        "learning_rate": [0.01, 0.1, 0.2],
        "n_estimators": [50, 100],
    }

    # Stratified K-Fold doesn't work if some classes have 1 element after splitting.
    # We oversampled the training set, so CV is safe.
    grid = GridSearchCV(xgb, param_grid, cv=3, scoring="f1_macro", n_jobs=-1)
    grid.fit(X_train_scaled, y_train_resampled)

    xgb_clf = grid.best_estimator_
    print(f"Best XGBoost Params: {grid.best_params_}")

    # Evaluate
    def evaluate(model, name):
        y_pred = model.predict(X_test_scaled)
        prec, rec, f1, support = precision_recall_fscore_support(
            y_test, y_pred, zero_division=0, labels=np.arange(num_classes)
        )
        macro_f1 = np.mean(f1)
        print(f"\n--- {name} Results ---")
        print(f"Macro F1: {macro_f1:.3f}")
        for i, class_name in enumerate(le.classes_):
            if support[i] > 0:
                print(f" {class_name:20} -> F1: {f1[i]:.3f} (Support: {support[i]})")
        return macro_f1, model

    rf_score, rf_model = evaluate(rf_clf, "RandomForest")
    xgb_score, xgb_model = evaluate(xgb_clf, "XGBoost")

    best_model = xgb_model if xgb_score >= rf_score else rf_model
    best_name = "XGBoost" if xgb_score >= rf_score else "RandomForest"

    print(f"\nSaving {best_name} as final model...")
    os.makedirs(model_dir, exist_ok=True)

    # For inference script compatibility, we wrap it in a dict with the label encoder
    model_bundle = {"model": best_model, "classes": le.classes_.tolist()}
    joblib.dump(model_bundle, os.path.join(model_dir, "classifier.joblib"))
    joblib.dump(scaler, os.path.join(model_dir, "scaler.joblib"))

    with open(os.path.join(model_dir, "feature_columns.json"), "w") as f:
        json.dump(df_feat.columns.tolist(), f)
    # The new pipeline needs simple valid labels list matching the classes array
    with open(os.path.join(model_dir, "label_columns.json"), "w") as f:
        json.dump(le.classes_.tolist(), f)

    # Write report
    report_md = f"""# ML Evaluation Report
Selected Model: {best_name} (Tuned via GridSearch & Oversampling)
Macro F1 Score: {max(rf_score, xgb_score):.3f}

Trained on {len(X_train_resampled)} balanced samples, evaluated on {len(X_test)} samples.
"""
    with open("training/evaluation_report.md", "w") as f:
        f.write(report_md)

    print("Training complete!")


if __name__ == "__main__":
    train()
