"""Run one genuine, sequential sham/intervention SITL pair."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .collector import collect_verified_logs
from .execution_integrity import attest_clean_source
from .executor import execute_run
from .experiment_io import write_experiment
from .frame_defaults import FRAME_CLASS_VALUES
from .owned_runner import OwnedSITLProcess
from .planner import build_paired_run_plans
from .runner import PymavlinkSITLSession
from .schema import ParameterSchema, canonical_json_bytes, sha256_file

PAIR_SCHEMA = "logdiagnosis.pair-commit/v1"
DEFAULT_ENDPOINT = "tcpin:127.0.0.1:14550"
FIXED_HOME = {
    "latitude": -35.363261,
    "longitude": 149.165230,
    "altitude_m": 584.0,
    "heading_deg": 353.0,
}


def _commit(ardupilot_root: Path) -> str:
    value = subprocess.check_output(
        ["git", "-C", str(ardupilot_root), "rev-parse", "HEAD"],
        text=True,
    ).strip().lower()
    if len(value) != 40 or any(char not in "0123456789abcdef" for char in value):
        raise RuntimeError("ArduPilot checkout did not resolve to a full commit")
    return value


def _bootstrap_plan(commit: str, binary_digest: str, frame: str) -> dict[str, Any]:
    try:
        frame_class = FRAME_CLASS_VALUES[frame]
    except KeyError as exc:
        raise ValueError(f"unsupported first-pair frame: {frame}") from exc
    return {
        "run_id": "inventory-capture",
        "ardupilot_revision": commit,
        "binary_sha256": binary_digest,
        "frame": frame,
        "fixed_home": FIXED_HOME,
        "simulation_start_unix_sec": 1_704_067_200,
        # The inventory probe must start in the requested frame. ArduCopter's
        # empty-defaults value is FRAME_CLASS=0, which is intentionally not a
        # supported quad/hexa/octa training lineage.
        "startup_parameters": {"FRAME_CLASS": float(frame_class)},
    }


def capture_schema(
    *,
    output_dir: Path,
    binary: Path,
    ardupilot_root: Path,
    endpoint: str,
    frame: str,
    timeout: float,
) -> ParameterSchema:
    """Capture live parameters from the exact binary before planning any run."""

    output_dir.mkdir(parents=True, exist_ok=True)
    binary_digest = sha256_file(binary)
    commit = _commit(ardupilot_root)
    attest_clean_source(ardupilot_root, commit)
    with tempfile.TemporaryDirectory(prefix="synthetic-inventory-") as temp_name:
        root = Path(temp_name)
        (root / "params").mkdir()
        plan = _bootstrap_plan(commit, binary_digest, frame)
        (root / "params" / "inventory-capture.parm").write_text(
            "".join(
                f"{name}={float(value):.12g}\n"
                for name, value in plan["startup_parameters"].items()
            ),
            encoding="utf-8",
        )
        owner = OwnedSITLProcess(
            experiment_dir=root,
            plan=plan,
            ardupilot_root=ardupilot_root,
            binary_path=binary,
            endpoint=endpoint,
            instance=0,
        )
        session = PymavlinkSITLSession(endpoint)
        try:
            owner.start()
            session.heartbeat(timeout)
            values = dict(session.fetch_parameters(timeout))
        finally:
            try:
                session.close()
            finally:
                owner.abort(timeout)
    inventory = output_dir / "parameter_inventory.parm"
    inventory.write_text(
        "".join(f"{name}={float(values[name]):.12g}\n" for name in sorted(values)),
        encoding="utf-8",
    )
    schema = ParameterSchema.from_inventory(
        inventory,
        ardupilot_commit=commit,
        binary_sha256=binary_digest,
    )
    schema.write(output_dir / "parameter_schema.json")
    return schema


def _execute_member(
    experiment_dir: Path,
    plan: dict[str, Any],
    *,
    binary: Path,
    ardupilot_root: Path,
    endpoint: str,
    timeout: float,
) -> dict[str, Any]:
    owner = OwnedSITLProcess(
        experiment_dir=experiment_dir,
        plan=plan,
        ardupilot_root=ardupilot_root,
        binary_path=binary,
        endpoint=endpoint,
        instance=0,
    )
    session = PymavlinkSITLSession(endpoint)
    try:
        owner.start()
        return execute_run(
            experiment_dir,
            str(plan["run_id"]),
            session=session,
            owner=owner,
            timeout=timeout,
            confirm_sitl=True,
        )
    finally:
        try:
            session.close()
        finally:
            owner.abort(timeout)


def _write_pair_commit(experiment_dir: Path, plans: list[dict[str, Any]]) -> Path:
    lineage = str(plans[0]["lineage_root_id"])
    if len(plans) != 2 or any(str(plan["lineage_root_id"]) != lineage for plan in plans):
        raise RuntimeError("first pair must contain exactly two members of one lineage")
    members = {}
    for plan in sorted(plans, key=lambda item: str(item["run_id"])):
        receipt = experiment_dir / "receipts" / str(plan["expected_receipt_filename"])
        if not receipt.is_file():
            raise RuntimeError(f"missing execution receipt for {plan['run_id']}")
        members[str(plan["run_id"])] = {
            "receipt_sha256": sha256_file(receipt),
            "attempt_dir": str(receipt.parent),
        }
    commit = {
        "schema": PAIR_SCHEMA,
        "lineage_root_id": lineage,
        "members": members,
        "fencing_epoch": 1,
    }
    commit["commit_sha256"] = hashlib.sha256(
        canonical_json_bytes(commit)
    ).hexdigest()
    safe = "".join(char if char.isalnum() or char in "._-" else "_" for char in lineage)
    destination = experiment_dir / "commits" / f"{safe}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(commit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


def run_first_pair(
    *,
    output_dir: str | Path,
    binary: str | Path,
    ardupilot_root: str | Path,
    scenario: str,
    seed: int = 20260823,
    endpoint: str = DEFAULT_ENDPOINT,
    frame: str = "quad",
    timeout: float = 120.0,
) -> dict[str, Any]:
    """Capture, plan, execute, seal, and collect one matched pair."""

    root = Path(output_dir).resolve()
    binary_path = Path(binary).resolve()
    source_root = Path(ardupilot_root).resolve()
    with tempfile.TemporaryDirectory(prefix="first-pair-capture-") as capture_name:
        capture_dir = Path(capture_name)
        schema = capture_schema(
            output_dir=capture_dir,
            binary=binary_path,
            ardupilot_root=source_root,
            endpoint=endpoint,
            frame=frame,
            timeout=timeout,
        )
        inventory_bytes = (capture_dir / "parameter_inventory.parm").read_bytes()
    plans = build_paired_run_plans(
        1,
        seed=seed,
        ardupilot_revision=schema.ardupilot_commit,
        scenarios=[scenario],
        parameter_schema=schema,
    )
    write_experiment(
        root,
        plans,
        seed=seed,
        ardupilot_revision=schema.ardupilot_commit,
        parameter_schema=schema,
    )
    (root / "parameter_inventory.parm").write_bytes(inventory_bytes)
    for plan in plans:
        _execute_member(
            root,
            plan,
            binary=binary_path,
            ardupilot_root=source_root,
            endpoint=endpoint,
            timeout=timeout,
        )
    commit_path = _write_pair_commit(root, plans)
    collection = collect_verified_logs(root, require_pair_commits=True)
    return {
        "schema": "logdiagnosis.first-pair/v1",
        "experiment_dir": str(root),
        "parameter_schema_sha256": schema.digest,
        "pair_commit": str(commit_path),
        "collection": collection,
    }
