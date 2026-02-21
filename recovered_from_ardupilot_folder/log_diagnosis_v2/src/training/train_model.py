import json
import os
import pickle
import sys
from typing import Dict, List, Optional, Tuple

import pandas as pd
import xgboost as xgb
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import GroupShuffleSplit, train_test_split

if __package__ in (None, ""):
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))


MODEL_ARTIFACT_VERSION = "2.0.0"
FEATURE_SCHEMA_VERSION = "2.0.0"

DEFAULT_LABEL_MAP = {
    0: "healthy",
    1: "vibration_high",
    2: "compass_interference",
    3: "battery_sag",
}


def _make_split(
    X: pd.DataFrame,
    y: pd.Series,
    groups: Optional[pd.Series],
    test_size: float,
    random_state: int,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series, str]:
    if groups is not None and groups.nunique() > 1:
        splitter = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=random_state)
        train_idx, test_idx = next(splitter.split(X, y, groups=groups))
        return (
            X.iloc[train_idx],
            X.iloc[test_idx],
            y.iloc[train_idx],
            y.iloc[test_idx],
            "group_session",
        )

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=test_size,
        random_state=random_state,
        stratify=y if y.nunique() > 1 else None,
    )
    return X_train, X_test, y_train, y_test, "stratified_random"


def train_model(
    data_path: str,
    model_output_path: str,
    metrics_output_path: Optional[str] = None,
    test_size: float = 0.2,
    random_state: int = 42,
) -> Dict[str, object]:
    """Train XGBoost multi-class classifier on dataset and export versioned artifact."""
    if not os.path.exists(data_path):
        raise FileNotFoundError(f"Dataset not found at {data_path}. Run build_dataset.py first.")

    df = pd.read_csv(data_path)
    if "target" not in df.columns:
        raise ValueError("Dataset must contain a 'target' column.")

    groups = df["session_id"] if "session_id" in df.columns else None

    feature_cols: List[str] = [c for c in df.columns if c not in ("target", "session_id", "source")]
    X = df[feature_cols].fillna(0.0)
    y_raw = df["target"].astype(int)

    # Ensure labels are contiguous for multi-class training.
    original_labels = sorted(set(int(v) for v in y_raw.unique()))
    label_to_index = {label: idx for idx, label in enumerate(original_labels)}
    index_to_label = {idx: label for label, idx in label_to_index.items()}
    y = y_raw.map(label_to_index).astype(int)

    X_train, X_test, y_train, y_test, split_strategy = _make_split(
        X=X,
        y=y,
        groups=groups,
        test_size=test_size,
        random_state=random_state,
    )

    num_classes = max(2, int(y.nunique()))

    model = xgb.XGBClassifier(
        objective="multi:softprob",
        eval_metric="mlogloss",
        num_class=num_classes,
        n_estimators=250,
        max_depth=6,
        learning_rate=0.08,
        subsample=0.9,
        colsample_bytree=0.9,
        random_state=random_state,
    )

    model.fit(X_train, y_train)

    preds = model.predict(X_test)
    accuracy = float(accuracy_score(y_test, preds))

    label_values = sorted(set(int(v) for v in y.unique()))
    label_map = {
        idx: DEFAULT_LABEL_MAP.get(index_to_label[idx], f"class_{index_to_label[idx]}")
        for idx in label_values
    }
    target_names = [label_map[idx] for idx in label_values]

    report_dict = classification_report(
        y_test,
        preds,
        labels=label_values,
        target_names=target_names,
        output_dict=True,
        zero_division=0,
    )

    report_text = classification_report(
        y_test,
        preds,
        labels=label_values,
        target_names=target_names,
        zero_division=0,
    )

    if metrics_output_path is None:
        base, _ = os.path.splitext(model_output_path)
        metrics_output_path = f"{base}.metrics.json"

    os.makedirs(os.path.dirname(os.path.abspath(model_output_path)), exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(metrics_output_path)), exist_ok=True)

    artifact = {
        "model": model,
        "features": feature_cols,
        "label_map": label_map,
        "metadata": {
            "artifact_version": MODEL_ARTIFACT_VERSION,
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "training_rows": int(len(df)),
            "feature_count": int(len(feature_cols)),
            "class_count": int(num_classes),
            "index_to_target": index_to_label,
            "split_strategy": split_strategy,
            "random_state": int(random_state),
            "test_size": float(test_size),
            "accuracy": accuracy,
        },
    }

    with open(model_output_path, "wb") as f:
        pickle.dump(artifact, f)

    metrics = {
        "data_path": os.path.abspath(data_path),
        "model_output_path": os.path.abspath(model_output_path),
        "accuracy": accuracy,
        "split_strategy": split_strategy,
        "classification_report": report_dict,
        "label_map": label_map,
        "index_to_target": index_to_label,
        "artifact_version": MODEL_ARTIFACT_VERSION,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
    }

    with open(metrics_output_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, sort_keys=True)

    print(f"Accuracy: {accuracy:.4f}")
    print(report_text)
    print(f"Artifact exported to {model_output_path}")
    print(f"Metrics exported to {metrics_output_path}")

    return metrics


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Train ArduPilot diagnosis model")
    parser.add_argument("--data", type=str, default="data/synthetic_logs.csv", help="Input dataset CSV")
    parser.add_argument("--output", type=str, default="models/model.pkl", help="Model artifact output path")
    parser.add_argument("--metrics-output", type=str, default=None, help="Metrics JSON output path")
    parser.add_argument("--test-size", type=float, default=0.2, help="Test split ratio")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    train_model(
        data_path=args.data,
        model_output_path=args.output,
        metrics_output_path=args.metrics_output,
        test_size=args.test_size,
        random_state=args.seed,
    )
