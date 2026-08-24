"""Measure hash-bound, real-lineage calibration for a development candidate.

This command is diagnostic only. It evaluates the exact real development-test
lineages recorded by a schema-v3 artifact and cannot authorize promotion.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import joblib
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.constants import FEATURE_NAMES, VALID_LABELS
from synthetic_data.evaluation_metrics import incident_metrics
from training.data_contract import (
    primary_label_for_row,
    require_known_source_types,
)

ECE_PASS_THRESHOLD = 0.08


def _hash_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_value(value: object) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _valid_hash(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def compute_ece(y_true: np.ndarray, probs: np.ndarray, n_bins: int = 10) -> float:
    """Return macro one-vs-rest ECE, retained for compatibility and tests."""

    edges = np.linspace(0.0, 1.0, n_bins + 1)
    errors: list[float] = []
    for class_id in range(probs.shape[1]):
        scores = probs[:, class_id]
        binary = (y_true == class_id).astype(float)
        error = 0.0
        for index, (low, high) in enumerate(zip(edges[:-1], edges[1:])):
            mask = (scores >= low) & (
                scores <= high if index == n_bins - 1 else scores < high
            )
            if mask.any():
                error += float(mask.mean()) * abs(
                    float(scores[mask].mean()) - float(binary[mask].mean())
                )
        errors.append(error)
    return float(np.mean(errors))


def aggregate_group_probabilities(
    y_true: np.ndarray, probs: np.ndarray, groups: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Apply deployed max-window aggregation to independent incident lineages."""

    y_true = np.asarray(y_true)
    probs = np.asarray(probs, dtype=float)
    groups = np.asarray(groups)
    if len(y_true) != len(probs) or len(y_true) != len(groups):
        raise ValueError("ECE arrays must have the same row count.")
    if len(y_true) == 0:
        return y_true, probs
    grouped_true: list[int] = []
    grouped_probs: list[np.ndarray] = []
    for group in np.unique(groups):
        indices = np.flatnonzero(groups == group)
        labels = set(y_true[indices].tolist())
        if len(labels) != 1:
            raise ValueError("An evaluation lineage contains contradictory labels.")
        grouped_true.append(int(y_true[indices[0]]))
        grouped_probs.append(np.max(probs[indices], axis=0))
    return np.asarray(grouped_true), np.asarray(grouped_probs)


def reliability_diagram(
    y_true: np.ndarray,
    probs: np.ndarray,
    class_names: list[str],
    output_path: str | Path,
) -> None:
    """Save a classwise development reliability diagram."""

    edges = np.linspace(0.0, 1.0, 11)
    columns = min(4, len(class_names))
    rows = (len(class_names) + columns - 1) // columns
    figure, axes = plt.subplots(rows, columns, figsize=(4 * columns, 4 * rows))
    flattened = np.atleast_1d(axes).flatten()
    for class_id, axis in zip(range(len(class_names)), flattened):
        scores = probs[:, class_id]
        binary = (y_true == class_id).astype(float)
        confidence: list[float] = []
        accuracy: list[float] = []
        for index, (low, high) in enumerate(zip(edges[:-1], edges[1:])):
            mask = (scores >= low) & (scores <= high if index == 9 else scores < high)
            if mask.any():
                confidence.append(float(scores[mask].mean()))
                accuracy.append(float(binary[mask].mean()))
        axis.plot([0, 1], [0, 1], "k--", lw=1, label="Perfect")
        if confidence:
            axis.plot(confidence, accuracy, "b-o", ms=4, label="Candidate")
        axis.set(xlim=(0, 1), ylim=(0, 1), title=class_names[class_id])
        axis.set_xlabel("Confidence")
        axis.set_ylabel("Observed frequency")
        axis.legend(fontsize=7)
    for axis in flattened[len(class_names) :]:
        axis.set_visible(False)
    figure.suptitle("Development reliability by real lineage")
    figure.tight_layout()
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(destination, dpi=120)
    plt.close(figure)


def _verify_artifact_files(root: Path, manifest: dict) -> None:
    if manifest.get("artifact_schema_version") != 3:
        raise ValueError("Calibration diagnostics require a schema-v3 artifact.")
    hashes = manifest.get("artifact_files")
    if not isinstance(hashes, dict):
        raise ValueError("Artifact manifest lacks file hashes.")
    required = (
        "classifier.joblib",
        "scaler.joblib",
        "feature_columns.json",
        "label_columns.json",
        "rule_thresholds.yaml",
    )
    for name in required:
        path = root / name
        expected = hashes.get(name)
        if not path.is_file() or not _valid_hash(expected):
            raise ValueError(f"Artifact hash is missing for {name}.")
        if _hash_file(path) != expected:
            raise ValueError(f"Artifact file hash mismatch for {name}.")


def load_model_and_predict(
    features_csv: str,
    labels_csv: str,
    groups_csv: str,
    model_dir: str = "models",
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Evaluate exactly the manifest-bound real development-test lineages."""

    root = Path(model_dir)
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError("Model manifest is required for lineage-bound calibration.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _verify_artifact_files(root, manifest)
    inputs = manifest.get("training_inputs", {})
    for field, path in (
        ("features_sha256", features_csv),
        ("labels_sha256", labels_csv),
        ("groups_sha256", groups_csv),
    ):
        if inputs.get(field) != _hash_file(path):
            raise ValueError(f"Calibration input does not match {field}.")

    feature_columns = json.loads(
        (root / "feature_columns.json").read_text(encoding="utf-8")
    )
    label_columns = json.loads(
        (root / "label_columns.json").read_text(encoding="utf-8")
    )
    if feature_columns != FEATURE_NAMES or not set(label_columns).issubset(
        VALID_LABELS
    ):
        raise ValueError(
            "Artifact feature or label schema is incompatible with runtime."
        )
    features = pd.read_csv(features_csv)
    labels = pd.read_csv(labels_csv)
    groups = pd.read_csv(groups_csv)
    if not (len(features) == len(labels) == len(groups)):
        raise ValueError("Features, labels, and groups must have equal row counts.")
    if (
        features.columns.tolist() != FEATURE_NAMES
        or labels.columns.tolist() != VALID_LABELS
    ):
        raise ValueError("Calibration CSV schemas differ from the runtime contract.")
    if "lineage_root_id" not in groups.columns:
        raise ValueError("Calibration groups require lineage_root_id.")
    lineages = groups["lineage_root_id"].fillna("").astype(str).str.strip().to_numpy()
    if any(not value for value in lineages):
        raise ValueError("Calibration groups contain blank lineage roots.")
    source_types = require_known_source_types(groups)
    physical = (
        groups.get("physical_flight_verified", pd.Series(False, index=groups.index))
        .fillna(False)
        .astype(str)
        .str.lower()
        .isin({"true", "1", "yes"})
        .to_numpy()
    )
    expected_hashes = manifest.get("evaluation", {}).get("test_lineage_hashes", [])
    if not expected_hashes or not all(_valid_hash(value) for value in expected_hashes):
        raise ValueError("Artifact manifest lacks exact real test-lineage hashes.")
    expected = set(expected_hashes)
    primary: list[str] = []
    keep: list[int] = []
    for position, (_, row) in enumerate(labels.iterrows()):
        preferred = groups.iloc[position].get("primary_label", "")
        label = primary_label_for_row(row, preferred=preferred, allowed=label_columns)
        if (
            label
            and source_types[position] == "real"
            and physical[position]
            and _hash_value(lineages[position]) in expected
        ):
            primary.append(label)
            keep.append(position)
    if not keep:
        raise ValueError("No verified physical rows match the artifact test lineages.")
    observed = {_hash_value(lineages[position]) for position in keep}
    if observed != expected:
        raise ValueError("Inputs do not contain exactly the artifact test lineages.")

    bundle = joblib.load(root / "classifier.joblib")
    scaler = joblib.load(root / "scaler.joblib")
    if not isinstance(bundle, dict) or bundle.get("classes") != label_columns:
        raise ValueError("Classifier bundle class order differs from its schema.")
    matrix = features.loc[keep, feature_columns].to_numpy(dtype=float)
    probabilities = bundle["model"].predict_proba(scaler.transform(matrix))
    target = np.asarray([label_columns.index(label) for label in primary])
    target, probabilities = aggregate_group_probabilities(
        target, probabilities, lineages[keep]
    )
    return target, probabilities, label_columns


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features-csv", default="training/features.csv")
    parser.add_argument("--labels-csv", default="training/labels.csv")
    parser.add_argument("--groups-csv", default="training/groups.csv")
    parser.add_argument("--model-dir", default="models")
    parser.add_argument("--output-diagram", default="docs/reliability_diagram.png")
    parser.add_argument("--report-path", default="training/ece_report.json")
    parser.add_argument("--target-ece", type=float, default=ECE_PASS_THRESHOLD)
    args = parser.parse_args()

    target, probabilities, classes = load_model_and_predict(
        args.features_csv, args.labels_csv, args.groups_csv, args.model_dir
    )
    metrics = incident_metrics(target, probabilities, classes)
    reliability_diagram(target, probabilities, classes, args.output_diagram)
    diagnostic_met = metrics["top_label_incident_ece"] <= args.target_ece
    root = Path(args.model_dir)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    evaluation = manifest.get("evaluation", {})
    report = {
        "schema": "logdiagnosis.calibration-development-diagnostic/v2",
        "status": "non_promoting_development_diagnostic",
        "release_authorized": False,
        "diagnostic_threshold_met": diagnostic_met,
        "target_top_label_incident_ece": args.target_ece,
        "metrics": metrics,
        "classes": classes,
        "independent_real_lineages": len(target),
        "calibration_per_class_real_lineages": evaluation.get(
            "calibration_per_class_real_lineages"
        ),
        "per_class_real_lineages": evaluation.get("per_class_real_lineages"),
        "every_declared_class_calibrated": evaluation.get(
            "every_declared_class_calibrated"
        ),
        "calibration_method_config_sha256": evaluation.get(
            "calibration_method_config_sha256"
        ),
        "method_config_sha256": evaluation.get("method_config_sha256"),
        "aggregation": "maximum raw class probability by lineage_root_id",
        "artifact_manifest_sha256": _hash_file(root / "manifest.json"),
        "classifier_sha256": _hash_file(root / "classifier.joblib"),
        "features_sha256": _hash_file(args.features_csv),
        "labels_sha256": _hash_file(args.labels_csv),
        "groups_sha256": _hash_file(args.groups_csv),
        "dataset_report_sha256": manifest.get("training_inputs", {}).get(
            "dataset_report_sha256"
        ),
        "split_ledger_sha256": manifest.get("training_inputs", {}).get(
            "split_ledger_sha256"
        ),
    }
    destination = Path(args.report_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if diagnostic_met else 1)


if __name__ == "__main__":
    main()
