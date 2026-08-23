"""Run leakage-resistant, non-promoting model experiments.

This command is intentionally separate from ``train_model.py``.  It trains
small, reproducible candidates on grouped splits and writes metrics only; it
never changes ``models/`` or the active production artifact.  The report is
useful when deciding whether more labelled incidents are needed before a
candidate can enter the release gate.

Example::

    python training/run_model_experiments.py \
      --output training/candidates/v3_unambiguous/experiment_report.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import joblib  # noqa: F401 - import check for the runtime environment
import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier
from sklearn.metrics import f1_score

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from training.data_contract import (  # noqa: E402
    effective_group_values,
    primary_label_for_row,
    require_known_source_types,
)
from training.evaluation_split import grouped_train_test_split  # noqa: E402


SPLIT_SEEDS = (1, 7, 21, 42, 99)
TARGET_F1 = 0.70
TARGET_ECE = 0.08
TARGET_HOLDOUT_GROUPS = 50


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_dataset(
    features_path: Path, labels_path: Path, groups_path: Path
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, list[str]]:
    features = pd.read_csv(features_path)
    labels = pd.read_csv(labels_path)
    groups_frame = pd.read_csv(groups_path)
    if len(features) != len(labels) or len(features) != len(groups_frame):
        raise ValueError("Features, labels, and groups must have the same number of rows.")
    if features.isna().any().any():
        raise ValueError("Feature CSV contains NaN values; rebuild the dataset first.")
    matrix = features.to_numpy(dtype=float)
    if not np.isfinite(matrix).all():
        raise ValueError("Feature CSV contains non-finite values.")

    labels_text: list[str] = []
    keep: list[int] = []
    source_types = require_known_source_types(groups_frame)
    allowed = labels.columns.tolist()
    for index, row in labels.iterrows():
        preferred = (
            groups_frame.iloc[index].get("primary_label", "")
            if "primary_label" in groups_frame.columns
            else ""
        )
        primary = primary_label_for_row(row, preferred=preferred, allowed=allowed)
        if primary and source_types[index] == "real":
            labels_text.append(primary)
            keep.append(index)
    if not keep:
        raise ValueError("Dataset has no trainable primary labels.")

    classes = sorted(set(labels_text))
    class_id = {name: index for index, name in enumerate(classes)}
    target = np.asarray([class_id[name] for name in labels_text], dtype=int)
    return (
        matrix[keep],
        target,
        effective_group_values(groups_frame)[keep],
        np.asarray(classes),
        features.columns.tolist(),
    )


def _aggregate_groups(
    probabilities: np.ndarray, target: np.ndarray, groups: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Apply the deployed max-window evidence contract at incident level."""

    grouped_probabilities: list[np.ndarray] = []
    grouped_target: list[int] = []
    for group in np.unique(groups):
        indices = np.flatnonzero(groups == group)
        grouped_probabilities.append(np.max(probabilities[indices], axis=0))
        grouped_target.append(int(target[indices[0]]))
    return np.asarray(grouped_probabilities), np.asarray(grouped_target, dtype=int)


def _ece(target: np.ndarray, probabilities: np.ndarray, bins: int = 10) -> float:
    """Match ``training.measure_ece`` (macro per-class incident ECE)."""

    if not len(target):
        return float("nan")
    edges = np.linspace(0.0, 1.0, bins + 1)
    class_errors: list[float] = []
    for class_id in range(probabilities.shape[1]):
        class_probability = probabilities[:, class_id]
        class_target = (target == class_id).astype(int)
        error = 0.0
        for low, high in zip(edges[:-1], edges[1:]):
            mask = (class_probability >= low) & (class_probability < high)
            if mask.any():
                error += mask.sum() * abs(
                    class_probability[mask].mean() - class_target[mask].mean()
                )
        class_errors.append(error / len(target))
    return float(np.mean(class_errors))


def _probabilities_for_model(model: Any, matrix: np.ndarray, class_count: int) -> np.ndarray:
    """Return all runtime class columns, even if a sparse fold omits one."""

    probabilities = np.asarray(model.predict_proba(matrix), dtype=float)
    output = np.zeros((len(matrix), class_count), dtype=float)
    output[:, np.asarray(model.classes_, dtype=int)] = probabilities
    return output


def _run_candidate(
    name: str,
    estimator_type: type,
    matrix: np.ndarray,
    target: np.ndarray,
    groups: np.ndarray,
    class_count: int,
) -> dict[str, Any]:
    split_results: list[dict[str, Any]] = []
    for seed in SPLIT_SEEDS:
        train_indices, test_indices = grouped_train_test_split(
            target, groups, random_state=seed
        )
        sample_weights = np.asarray(
            [1.0 / np.sum(groups[train_indices] == group) for group in groups[train_indices]]
        )
        estimator = estimator_type(
            n_estimators=400,
            min_samples_leaf=2,
            class_weight="balanced",
            max_features="sqrt",
            n_jobs=4,
            random_state=42,
        )
        estimator.fit(matrix[train_indices], target[train_indices], sample_weight=sample_weights)
        probabilities = _probabilities_for_model(
            estimator, matrix[test_indices], class_count
        )
        group_probabilities, group_target = _aggregate_groups(
            probabilities, target[test_indices], groups[test_indices]
        )
        predictions = group_probabilities.argmax(axis=1)
        split_results.append(
            {
                "seed": seed,
                "train_groups": int(len(np.unique(groups[train_indices]))),
                "test_groups": int(len(np.unique(groups[test_indices]))),
                "window_rows_train": int(len(train_indices)),
                "window_rows_test": int(len(test_indices)),
                "macro_f1_log": float(
                    f1_score(
                        group_target,
                        predictions,
                        average="macro",
                        labels=np.arange(class_count),
                        zero_division=0,
                    )
                ),
                "incident_ece": _ece(group_target, group_probabilities),
            }
        )

    f1_values = np.asarray([item["macro_f1_log"] for item in split_results])
    ece_values = np.asarray([item["incident_ece"] for item in split_results])
    return {
        "name": name,
        "estimator": estimator_type.__name__,
        "parameters": {
            "n_estimators": 400,
            "min_samples_leaf": 2,
            "class_weight": "balanced",
            "max_features": "sqrt",
            "sample_weight": "inverse_window_count_per_source_group",
            "random_state": 42,
        },
        "splits": split_results,
        "mean_macro_f1_log": float(f1_values.mean()),
        "std_macro_f1_log": float(f1_values.std()),
        "mean_incident_ece": float(ece_values.mean()),
        "std_incident_ece": float(ece_values.std()),
        "release_gate": {
            "pass": bool(
                f1_values.mean() >= TARGET_F1
                and ece_values.mean() <= TARGET_ECE
                and min(item["test_groups"] for item in split_results)
                >= TARGET_HOLDOUT_GROUPS
            ),
            "macro_f1_target": TARGET_F1,
            "ece_target": TARGET_ECE,
            "holdout_group_target": TARGET_HOLDOUT_GROUPS,
        },
    }


def _write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# Non-promoting grouped model experiments",
        "",
        "These experiments never modify the active `models/` artifact. Metrics are",
        "incident-level: all windows from one source group stay in one split, then",
        "probabilities are aggregated with the deployed max-window contract.",
        "",
        f"Dataset: `{report['dataset']['rows']} labelled windows / "
        f"{report['dataset']['groups']} source groups`.",
        f"Split seeds: `{', '.join(str(seed) for seed in report['split_seeds'])}`.",
        "",
        "| Candidate | Mean Macro F1 | Mean incident ECE | Gate |",
        "|---|---:|---:|---|",
    ]
    for candidate in report["candidates"]:
        gate = "PASS" if candidate["release_gate"]["pass"] else "FAIL"
        lines.append(
            f"| `{candidate['name']}` | {candidate['mean_macro_f1_log']:.3f} "
            f"± {candidate['std_macro_f1_log']:.3f} | "
            f"{candidate['mean_incident_ece']:.3f} ± "
            f"{candidate['std_incident_ece']:.3f} | {gate} |"
        )
    lines.extend(
        [
            "",
            "No candidate is promoted: the current data does not meet the release",
            "requirements of Macro F1 ≥ 0.70, incident ECE ≤ 0.08, and at least 50",
            "independent holdout incidents. Collect independently expert-labelled",
            "logs—especially rare PID/power incidents—before retraining.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def run(args: argparse.Namespace) -> dict[str, Any]:
    feature_path = Path(args.features_csv)
    labels_path = Path(args.labels_csv)
    groups_path = Path(args.groups_csv)
    matrix, target, groups, classes, feature_names = _load_dataset(
        feature_path, labels_path, groups_path
    )
    report = {
        "schema_version": 1,
        "non_promoting": True,
        "split_seeds": list(SPLIT_SEEDS),
        "aggregation": "max_raw_probability_per_source_group",
        "dataset": {
            "features_sha256": _sha256(feature_path),
            "labels_sha256": _sha256(labels_path),
            "groups_sha256": _sha256(groups_path),
            "rows": int(len(matrix)),
            "groups": int(len(np.unique(groups))),
            "features": int(len(feature_names)),
            "classes": classes.tolist(),
            "class_group_counts": {
                str(name): int(
                    len({groups[index] for index in np.flatnonzero(target == class_id)})
                )
                for class_id, name in enumerate(classes)
            },
        },
        "candidates": [
            _run_candidate(
                "extra_trees_group_weighted_v1",
                ExtraTreesClassifier,
                matrix,
                target,
                groups,
                len(classes),
            ),
            _run_candidate(
                "random_forest_group_weighted_v1",
                RandomForestClassifier,
                matrix,
                target,
                groups,
                len(classes),
            ),
        ],
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    markdown_path = output_path.with_suffix(".md")
    _write_markdown(report, markdown_path)
    print(json.dumps(report, indent=2))
    print(f"JSON report: {output_path}")
    print(f"Markdown report: {markdown_path}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features-csv", default="training/features.csv")
    parser.add_argument("--labels-csv", default="training/labels.csv")
    parser.add_argument("--groups-csv", default="training/groups.csv")
    parser.add_argument(
        "--output",
        default="training/experiments/model_experiment_report.json",
    )
    run(parser.parse_args())


if __name__ == "__main__":
    main()
