"""Immutable experiment artifact writer separated from plan generation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .contracts import validate_contract
from .planner import (
    GENERATOR_VERSION,
    MANIFEST_SCHEMA,
    RESEARCH_BASIS,
    _immutable_revision,
    _safe_plan,
)
from .schema import ParameterSchema


def _atomic_text(path: Path, text: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _pending_row(plan: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "filename": plan["expected_log_filename"],
        "labels": [plan["label"]],
        "confidence": "unverified",
        "source_type": plan["source_type"],
        "source_group": plan["source_group"],
        "lineage_root_id": plan["lineage_root_id"],
        "label_origin": plan["label_origin"],
        "trainable": False,
        "verification_status": "planned",
        "simulation_family": plan["scenario"],
        "scenario_sampling_seed": plan["scenario_sampling_seed"],
        "generator_version": plan["generator_version"],
        "planned_fault_onset_sec": plan["planned_fault_onset_sec"],
        "ardupilot_revision": plan["ardupilot_revision"],
        "run_fingerprint": plan["run_fingerprint"],
    }


def write_experiment(
    output_dir: str | Path,
    plans: Sequence[Mapping[str, Any]],
    *,
    seed: int,
    ardupilot_revision: str,
    parameter_schema: ParameterSchema | None = None,
) -> dict[str, Path]:
    if not plans:
        raise ValueError("at least one run plan is required")
    for plan in plans:
        _safe_plan(plan)
    run_ids = [str(plan["run_id"]) for plan in plans]
    if len(run_ids) != len(set(run_ids)):
        raise ValueError("run IDs must be unique")
    revision = _immutable_revision(ardupilot_revision)
    if any(str(plan["ardupilot_revision"]) != revision for plan in plans):
        raise ValueError("all plans must use the experiment ArduPilot revision")
    if parameter_schema and parameter_schema.ardupilot_commit != revision.lower():
        raise ValueError("parameter schema commit does not match the experiment")

    root = Path(output_dir)
    manifest_path = root / "experiment_manifest.json"
    existing_items = list(root.iterdir()) if root.exists() else []
    if existing_items and not manifest_path.exists():
        raise FileExistsError("refusing to plan into a non-empty unowned directory")
    root.mkdir(parents=True, exist_ok=True)
    for directory in ("params", "injections", "logs", "receipts", "quarantine"):
        (root / directory).mkdir(exist_ok=True)

    manifest = {
        "schema": MANIFEST_SCHEMA,
        "generator_version": GENERATOR_VERSION,
        "seed": int(seed),
        "ardupilot_revision": revision,
        "parameter_schema_sha256": parameter_schema.digest
        if parameter_schema
        else None,
        "binary_sha256": parameter_schema.binary_sha256 if parameter_schema else None,
        "capability_status": "verified" if parameter_schema else "unverified",
        "research_basis": RESEARCH_BASIS,
        "evaluation_policy": (
            "training_only; calibration, threshold selection, and release holdout are real-only"
        ),
        "unsupported_claims": [
            "real incident prevalence",
            "specific physical component defect",
            "real-world accuracy improvement without a new blinded confirmation cohort",
        ],
        "runs": [dict(plan) for plan in plans],
    }
    if parameter_schema is not None:
        validate_contract(manifest, "experiment_manifest.schema.json")
    manifest_text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    if manifest_path.exists():
        if manifest_path.read_text(encoding="utf-8") != manifest_text:
            raise FileExistsError(
                "an experiment with different immutable inputs already exists"
            )
        return _outputs(root, manifest_path)

    _atomic_text(manifest_path, manifest_text)
    manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    _atomic_text(root / "experiment_manifest.sha256", manifest_hash + "\n")
    if parameter_schema:
        parameter_schema.write(root / "parameter_schema.json")
    pending: dict[str, Any] = {
        "schema": "logdiagnosis.pending-ground-truth/v2",
        "logs": [],
    }
    for plan in plans:
        pending["logs"].append(_pending_row(plan))
        parameter_lines = [
            f"{name}={float(value):.12g}"
            for name, value in plan["startup_parameters"].items()
        ]
        _atomic_text(
            root / "params" / f"{plan['run_id']}.parm",
            "\n".join(parameter_lines) + ("\n" if parameter_lines else ""),
        )
        injection = {
            "schema": "logdiagnosis.sitl-injection/v2",
            "manifest_sha256": manifest_hash,
            "run_id": plan["run_id"],
            "run_fingerprint": plan["run_fingerprint"],
            "planned_fault_onset_sec": plan["planned_fault_onset_sec"],
            "temporal_profile": plan["temporal_profile"],
            "parameters": plan["injection_parameters"],
        }
        _atomic_text(
            root / "injections" / f"{plan['run_id']}.json",
            json.dumps(injection, indent=2, sort_keys=True) + "\n",
        )
    _atomic_text(
        root / "ground_truth_pending.json",
        json.dumps(pending, indent=2, sort_keys=True) + "\n",
    )
    return _outputs(root, manifest_path)


def _outputs(root: Path, manifest_path: Path) -> dict[str, Path]:
    return {
        "manifest": manifest_path,
        "manifest_hash": root / "experiment_manifest.sha256",
        "pending_ground_truth": root / "ground_truth_pending.json",
        "logs": root / "logs",
        "receipts": root / "receipts",
    }
