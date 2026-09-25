"""Reproducible evaluation for the real-log benchmark (paper harness v1).

Every run writes one JSON file that records the git commit, a hash of every
input, the seeds and the metrics, so each published number can be traced in
``docs/EVIDENCE_LEDGER.md``.

Two families of results:

1. **Split-protocol study (leakage).** The same tree models are evaluated
   out-of-fold under three protocols that differ only in how windows are
   grouped: random windows, grouped by log file, and grouped by incident
   (source thread). Log-level scores use the deployed max-window rule.
2. **Rule-engine comparison.** The rule engine alone, and rules passed through
   the hybrid fusion with CITA temporal arbitration on and off. No trained
   model is involved, so these runs cannot leak training data. The shipped
   ML artifact is also scored, but it was trained on logs in this set, so
   that result is reported as contaminated and must not be cited as
   performance.

Macro-F1 is computed over the classes present in the evaluated labels.
Confidence intervals are 95% percentile intervals from an incident-cluster
bootstrap (incidents are resampled, not logs).

Example::

    python training/paper_eval.py --output data/benchmark/results/paper_eval_v1.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import StratifiedGroupKFold, StratifiedKFold

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from training.run_model_experiments import _ece  # noqa: E402

SEEDS = (1, 7, 21, 42, 99)
N_SPLITS = 5
BOOTSTRAP_REPS = 2000
NO_DIAGNOSIS = "__none__"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_state() -> dict[str, Any]:
    def run(*cmd: str) -> str:
        return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True).stdout.strip()

    return {
        "commit": run("git", "rev-parse", "HEAD"),
        "dirty": bool(run("git", "status", "--porcelain", "--untracked-files=no")),
    }


def macro_f1(y_true: list[str], y_pred: list[str]) -> float:
    labels = sorted(set(y_true))
    return float(f1_score(y_true, y_pred, labels=labels, average="macro", zero_division=0))


def cluster_bootstrap(
    y_true: list[str],
    y_pred: list[str],
    clusters: list[str],
    metric: Callable[[list[str], list[str]], float],
    seed: int = 20260925,
) -> dict[str, float]:
    """95% percentile CI, resampling whole incidents with replacement."""
    rng = np.random.default_rng(seed)
    by_cluster: dict[str, list[int]] = {}
    for index, cluster in enumerate(clusters):
        by_cluster.setdefault(cluster, []).append(index)
    keys = list(by_cluster)
    values = []
    for _ in range(BOOTSTRAP_REPS):
        picked = rng.choice(len(keys), size=len(keys), replace=True)
        indices = [i for k in picked for i in by_cluster[keys[k]]]
        values.append(metric([y_true[i] for i in indices], [y_pred[i] for i in indices]))
    low, high = np.percentile(values, [2.5, 97.5])
    return {"low": float(low), "high": float(high), "reps": BOOTSTRAP_REPS}


def summarise(
    y_true: list[str], y_pred: list[str], clusters: list[str]
) -> dict[str, Any]:
    return {
        "n_logs": len(y_true),
        "n_incidents": len(set(clusters)),
        "macro_f1": macro_f1(y_true, y_pred),
        "macro_f1_ci95": cluster_bootstrap(y_true, y_pred, clusters, macro_f1),
        "top1_accuracy": float(accuracy_score(y_true, y_pred)),
        "coverage": float(np.mean([p != NO_DIAGNOSIS for p in y_pred])),
        "per_class": {
            label: {
                "n": int(sum(t == label for t in y_true)),
                "recall": float(
                    np.mean([p == label for t, p in zip(y_true, y_pred) if t == label])
                ),
            }
            for label in sorted(set(y_true))
        },
    }


# ---------------------------------------------------------------- split study


def load_windows(derived: Path) -> tuple[np.ndarray, pd.DataFrame]:
    features = pd.read_csv(derived / "features.csv")
    groups = pd.read_csv(derived / "groups.csv", keep_default_na=False)
    if len(features) != len(groups):
        raise ValueError("features.csv and groups.csv row counts differ")
    matrix = features.to_numpy(dtype=float)
    if not np.isfinite(matrix).all():
        raise ValueError("non-finite feature values; rebuild the dataset")
    return matrix, groups


def make_model(kind: str, seed: int) -> Any:
    cls = ExtraTreesClassifier if kind == "ExtraTrees" else RandomForestClassifier
    return cls(
        n_estimators=400,
        min_samples_leaf=2,
        class_weight="balanced",
        max_features="sqrt",
        n_jobs=-1,
        random_state=seed,
    )


def out_of_fold(
    matrix: np.ndarray,
    target: np.ndarray,
    split_groups: np.ndarray | None,
    weight_groups: np.ndarray,
    kind: str,
    seed: int,
    n_classes: int,
) -> np.ndarray:
    """Out-of-fold class probabilities for every window row."""
    if split_groups is None:
        splitter = StratifiedKFold(n_splits=N_SPLITS, shuffle=True, random_state=seed)
        folds = splitter.split(matrix, target)
    else:
        splitter = StratifiedGroupKFold(n_splits=N_SPLITS, shuffle=True, random_state=seed)
        folds = splitter.split(matrix, target, split_groups)
    probabilities = np.zeros((len(target), n_classes))
    for train, test in folds:
        # Each source log contributes equal total weight, as in production.
        counts = pd.Series(weight_groups[train]).value_counts()
        weights = np.asarray([1.0 / counts[g] for g in weight_groups[train]])
        model = make_model(kind, seed)
        model.fit(matrix[train], target[train], sample_weight=weights)
        fold_probs = np.zeros((len(test), n_classes))
        fold_probs[:, model.classes_] = model.predict_proba(matrix[test])
        probabilities[test] = fold_probs
    return probabilities


def split_study(derived: Path) -> dict[str, Any]:
    matrix, groups = load_windows(derived)
    classes = sorted(groups["primary_label"].unique())
    target = np.asarray([classes.index(label) for label in groups["primary_label"]])
    logs = groups["source_log"].to_numpy()
    incidents = groups["source_group"].to_numpy()
    protocols = {
        "window_random": None,
        "log_grouped": logs,
        "incident_grouped": incidents,
    }
    log_names = sorted(set(logs))
    log_incident = {log: incidents[logs == log][0] for log in log_names}
    log_label = {log: groups["primary_label"][logs == log].iloc[0] for log in log_names}

    results: dict[str, Any] = {}
    for kind in ("RandomForest", "ExtraTrees"):
        for name, split_groups in protocols.items():
            per_seed = []
            for seed in SEEDS:
                probs = out_of_fold(
                    matrix, target, split_groups, logs, kind, seed, len(classes)
                )
                window_pred = [classes[i] for i in probs.argmax(axis=1)]
                window_true = list(groups["primary_label"])
                log_probs = np.asarray([probs[logs == log].max(axis=0) for log in log_names])
                log_pred = [classes[i] for i in log_probs.argmax(axis=1)]
                log_true = [log_label[log] for log in log_names]
                clusters = [log_incident[log] for log in log_names]
                entry = {
                    "seed": seed,
                    "window_macro_f1": macro_f1(window_true, window_pred),
                    "log": summarise(log_true, log_pred, clusters),
                    "log_ece": _ece(
                        np.asarray([classes.index(t) for t in log_true]),
                        log_probs / np.clip(log_probs.sum(axis=1, keepdims=True), 1e-12, None),
                    ),
                }
                per_seed.append(entry)
            f1s = np.asarray([e["log"]["macro_f1"] for e in per_seed])
            eces = np.asarray([e["log_ece"] for e in per_seed])
            wf1 = np.asarray([e["window_macro_f1"] for e in per_seed])
            results[f"{kind}/{name}"] = {
                "model": kind,
                "protocol": name,
                "log_macro_f1_mean": float(f1s.mean()),
                "log_macro_f1_std": float(f1s.std()),
                "log_ece_mean": float(eces.mean()),
                "window_macro_f1_mean": float(wf1.mean()),
                "seeds": per_seed,
            }
    return {
        "classes": classes,
        "n_windows": int(len(target)),
        "n_logs": len(log_names),
        "n_incidents": len(set(incidents)),
        "folds": N_SPLITS,
        "seeds": list(SEEDS),
        "results": results,
    }


# ----------------------------------------------------------- engine comparison


class _NoML:
    available = False

    def predict(self, _features: Any) -> list:
        return []


def _top(diagnoses: list[dict]) -> str:
    return str(diagnoses[0]["failure_type"]) if diagnoses else NO_DIAGNOSIS


def extract_log_features(ground_truth: dict, dataset_dir: Path, cache: Path) -> dict[str, dict]:
    """Parse each benchmark log once; cache the full-log feature dicts."""
    if cache.exists():
        cached = json.loads(cache.read_text(encoding="utf-8"))
        if cached.get("ground_truth_sha256") == ground_truth["_sha256"]:
            return cached["features"]
    from src.features.pipeline import FeaturePipeline
    from src.parser.bin_parser import LogParser

    pipeline = FeaturePipeline()
    features: dict[str, dict] = {}
    for entry in ground_truth["logs"]:
        parsed = LogParser(str(dataset_dir / entry["filename"])).parse()
        extracted = pipeline.extract(parsed)
        features[entry["filename"]] = {
            key: (float(value) if isinstance(value, (int, float)) else value)
            for key, value in extracted.items()
            if isinstance(value, (int, float, str, bool)) or value is None
        }
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(
        json.dumps(
            {"ground_truth_sha256": ground_truth["_sha256"], "features": features},
            indent=1,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return features


def engine_study(ground_truth: dict, features: dict[str, dict]) -> dict[str, Any]:
    from src.diagnosis.hybrid_engine import HybridEngine
    from src.diagnosis.rule_engine import RuleEngine

    no_ml: Any = _NoML()
    rules = RuleEngine()

    def rules_ranked(features: dict) -> list:
        # The rule engine does not order its findings; rank by confidence.
        return sorted(rules.diagnose(features), key=lambda d: -float(d.get("confidence", 0.0)))

    # Hybrid output is kept in the engine's own order: CITA places the
    # selected root cause first, which is not always the most confident.
    engines: dict[str, Callable[[dict], list]] = {
        "rules_only": rules_ranked,
        "rules_fused_with_cita": HybridEngine(ml_classifier=no_ml).diagnose,
        "rules_fused_without_cita": HybridEngine(
            ml_classifier=no_ml, temporal_arbitration=False
        ).diagnose,
        "shipped_hybrid_CONTAMINATED": HybridEngine().diagnose,
    }
    y_true = [entry["labels"][0] for entry in ground_truth["logs"]]
    clusters = [entry["incident_id"] for entry in ground_truth["logs"]]
    results: dict[str, Any] = {}
    for name, diagnose in engines.items():
        y_pred = []
        for entry in ground_truth["logs"]:
            y_pred.append(_top(diagnose(dict(features[entry["filename"]]))))
        results[name] = summarise(y_true, y_pred, clusters)
        results[name]["predictions"] = dict(
            zip([entry["filename"] for entry in ground_truth["logs"]], y_pred)
        )
    results["shipped_hybrid_CONTAMINATED"]["warning"] = (
        "The shipped classifier was trained on logs in this benchmark. "
        "This is a training-set score and must not be cited as performance."
    )
    cita_changed = [
        name
        for name in results["rules_fused_with_cita"]["predictions"]
        if results["rules_fused_with_cita"]["predictions"][name]
        != results["rules_fused_without_cita"]["predictions"][name]
    ]
    correct = {
        name: int(
            sum(
                results[name]["predictions"][entry["filename"]] == entry["labels"][0]
                for entry in ground_truth["logs"]
            )
        )
        for name in results
    }
    return {
        "results": results,
        "correct_top1_counts": correct,
        "cita_changed_top1_on_logs": cita_changed,
    }


def chance_baselines(ground_truth: dict) -> dict[str, Any]:
    """Anchors: what trivial predictors score on the same logs."""
    y_true = [entry["labels"][0] for entry in ground_truth["logs"]]
    clusters = [entry["incident_id"] for entry in ground_truth["logs"]]
    majority = max(sorted(set(y_true)), key=y_true.count)
    rng = np.random.default_rng(20260925)
    labels = sorted(set(y_true))
    freqs = np.asarray([y_true.count(label) for label in labels], dtype=float) / len(y_true)
    random_f1 = [
        macro_f1(y_true, list(rng.choice(labels, size=len(y_true), p=freqs)))
        for _ in range(BOOTSTRAP_REPS)
    ]
    return {
        "majority_class": {"label": majority, **summarise(y_true, [majority] * len(y_true), clusters)},
        "frequency_random_macro_f1": {
            "mean": float(np.mean(random_f1)),
            "p95": float(np.percentile(random_f1, 95)),
            "draws": BOOTSTRAP_REPS,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--ground-truth", default="data/benchmark/ground_truth_real_v1.json")
    parser.add_argument("--derived-dir", default="data/benchmark/derived")
    parser.add_argument("--dataset-dir", default="data/raw/benchmark_v1")
    parser.add_argument("--output", default="data/benchmark/results/paper_eval_v1.json")
    parser.add_argument("--skip-engines", action="store_true")
    args = parser.parse_args()

    gt_path = ROOT / args.ground_truth
    derived = ROOT / args.derived_dir
    ground_truth = json.loads(gt_path.read_text(encoding="utf-8"))
    ground_truth["_sha256"] = sha256_file(gt_path)
    inputs = {
        str(path.relative_to(ROOT)): sha256_file(path)
        for path in [gt_path, *sorted(derived.glob("*.csv"))]
    }

    report: dict[str, Any] = {
        "schema": "logdiagnosis.paper-eval/v1",
        "git": git_state(),
        "inputs_sha256": inputs,
        "metric_notes": {
            "macro_f1": "over classes present in the evaluated labels",
            "ci": "95% percentile, incident-cluster bootstrap",
            "log_aggregation": "max window probability per log (deployed contract)",
            "ece": "macro per-class ECE, 10 bins, on normalised log probabilities",
        },
        "chance_baselines": chance_baselines(ground_truth),
        "split_study": split_study(derived),
    }
    if not args.skip_engines:
        features = extract_log_features(
            ground_truth, ROOT / args.dataset_dir, derived / "log_features.json"
        )
        report["engine_study"] = engine_study(ground_truth, features)

    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    brief = {
        key: {
            "log_f1": round(value["log_macro_f1_mean"], 3),
            "sd": round(value["log_macro_f1_std"], 3),
            "window_f1": round(value["window_macro_f1_mean"], 3),
            "ece": round(value["log_ece_mean"], 3),
        }
        for key, value in report["split_study"]["results"].items()
    }
    print(json.dumps(brief, indent=2))
    anchors = report["chance_baselines"]
    print(
        "majority_class", round(anchors["majority_class"]["macro_f1"], 3),
        "frequency_random mean/p95",
        round(anchors["frequency_random_macro_f1"]["mean"], 3),
        round(anchors["frequency_random_macro_f1"]["p95"], 3),
    )
    if "engine_study" in report:
        for name, value in report["engine_study"]["results"].items():
            print(name, round(value["macro_f1"], 3), value["macro_f1_ci95"], value["coverage"])
    print("wrote", output.relative_to(ROOT))


if __name__ == "__main__":
    main()
