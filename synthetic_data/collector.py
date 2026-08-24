"""Fail-closed collection of causally verified ArduPilot DataFlash outputs."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .catalog import SCENARIOS
from .collector_checks import (
    _causal_evidence,
    _observed_injection,
    _validate_receipt,
)
from .contracts import validate_contract
from .dataflash_checks import (
    inspect_log as _inspect_log,
    manifestation_predicate_sha256 as _manifestation_predicate_sha256,
)
from .integrity import (
    VerificationError,
    atomic_json as _atomic_json,
    read_json as _read_json,
    safe_child as _safe_child,
)
from .planner import MANIFEST_SCHEMA, _safe_plan
from .schema import ParameterSchema, sha256_file

COLLECTION_SCHEMA = "logdiagnosis.sitl-collection-receipt/v2"
GROUND_TRUTH_SCHEMA = "logdiagnosis.verified-sitl-ground-truth/v2"
PAIR_COMMIT_SCHEMA = "logdiagnosis.pair-commit/v1"


def _require_pair_commit(
    root: Path,
    plan: Mapping[str, Any],
    *,
    commits_dir: Path,
) -> None:
    """Fail closed unless a sealed pair-commit pointer covers this run.

    A lineage is trainable only when its ``pair-commit/v1`` pointer exists,
    binds every member's on-disk execution receipt by exact SHA256, and was
    produced under the coordinator's fencing epoch. This makes a lone
    surviving arm untrainable even if its own receipt is perfect.
    """

    lineage = str(plan.get("lineage_root_id", ""))
    role = str(plan.get("pair_role", ""))
    if not lineage or not role:
        return  # unpaired runs carry no pair contract
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in lineage)
    commit_path = commits_dir / f"{safe}.json"
    if not commit_path.is_file():
        raise VerificationError(
            f"lineage {lineage} has no sealed pair-commit pointer; "
            "a lone surviving arm is never trainable"
        )
    commit = _read_json(commit_path, maximum_bytes=1024 * 1024)
    if commit.get("schema") != PAIR_COMMIT_SCHEMA:
        raise VerificationError("unsupported pair-commit schema")
    members = commit.get("members")
    run_id = str(plan["run_id"])
    if not isinstance(members, dict) or run_id not in members:
        raise VerificationError(
            f"pair-commit for {lineage} does not bind this run ({run_id})"
        )
    for member_run_id, member in sorted(members.items()):
        member_receipt = _safe_child(
            root / "receipts",
            f"{member_run_id}.execution.json",
            ".json",
        )
        if not member_receipt.is_file():
            raise VerificationError(
                f"pair-commit member {member_run_id} lacks an on-disk receipt"
            )
        actual = sha256_file(member_receipt)
        if str(member.get("receipt_sha256", "")) != actual:
            raise VerificationError(
                f"pair-commit binding for {member_run_id} does not match the "
                "sealed execution receipt"
            )


def _ground_truth_row(
    plan: Mapping[str, Any],
    *,
    manifest_sha256: str,
    schema: ParameterSchema,
    log_evidence: Mapping[str, Any],
    onset_sec: float | None,
    observed_parameters: list[dict[str, Any]],
    causal_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "run_id": plan["run_id"],
        "filename": plan["expected_log_filename"],
        "labels": [plan["label"]],
        "confidence": "high",
        "source_type": "sitl",
        "source_group": plan["source_group"],
        "lineage_root_id": plan["lineage_root_id"],
        "label_origin": plan["label_origin"],
        "human_verified": False,
        "trainable": True,
        "verification_status": "accepted",
        "simulation_family": plan["scenario"],
        "scenario_sampling_seed": plan["scenario_sampling_seed"],
        "generator_version": plan["generator_version"],
        "conditioning_mode": "pure_simulation",
        "conditioning_real_lineage_id": "",
        "near_duplicate_cluster_id": "",
        "vehicle_frame": plan["frame"],
        "firmware_commit": plan["ardupilot_revision"],
        "flight_phase": "guided_takeoff_hover_land",
        "scenario": plan["scenario"],
        "pair_role": plan["role"],
        "paired_with": plan["paired_with"],
        "manifestation_predicate_sha256": _manifestation_predicate_sha256(),
        "planned_fault_onset_sec": plan["planned_fault_onset_sec"],
        "fault_onset_sec": onset_sec,
        "ardupilot_revision": plan["ardupilot_revision"],
        "run_fingerprint": plan["run_fingerprint"],
        "manifest_sha256": manifest_sha256,
        "parameter_schema_sha256": schema.digest,
        "artifact_sha256": log_evidence["sha256"],
        "sitl_evidence": dict(log_evidence),
        "observed_parameter_changes": observed_parameters,
        "causal_evidence": dict(causal_evidence),
        "causal_chain": plan["causal_chain"],
        "non_claims": plan["non_claims"],
    }


def collect_verified_logs(
    output_dir: str | Path,
    *,
    include_experimental: bool = False,
    require_pair_commits: bool | None = None,
) -> dict[str, Any]:
    """Promote only receipt-bound, observable, non-duplicate SITL runs.

    When ``require_pair_commits`` is None, pair-commit enforcement activates
    automatically whenever a ``commits/`` directory exists beside the
    experiment; passing True enforces unconditionally and False disables it
    (development fixtures only).
    """

    root = Path(output_dir)
    commits_dir = root / "commits"
    if require_pair_commits is None:
        require_pair_commits = commits_dir.is_dir()
    manifest_path = root / "experiment_manifest.json"
    manifest = _read_json(manifest_path)
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise VerificationError("unsupported experiment manifest schema")
    validate_contract(manifest, "experiment_manifest.schema.json")
    manifest_sha256 = sha256_file(manifest_path)
    recorded_hash = (
        (root / "experiment_manifest.sha256")
        .read_text(encoding="ascii")
        .strip()
        .lower()
    )
    if recorded_hash != manifest_sha256:
        raise VerificationError("experiment manifest hash sidecar does not match")
    if manifest.get("capability_status") != "verified":
        raise VerificationError(
            "experiment was planned without an exact parameter schema"
        )
    schema = ParameterSchema.read(root / "parameter_schema.json")
    if manifest.get("parameter_schema_sha256") != schema.digest:
        raise VerificationError("experiment parameter-schema hash does not match")
    if manifest.get("ardupilot_revision", "").lower() != schema.ardupilot_commit:
        raise VerificationError("experiment revision does not match parameter schema")

    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen_payloads: dict[str, str] = {}
    for plan in manifest.get("runs", []):
        run_id = str(plan.get("run_id", "unknown"))
        try:
            _safe_plan(plan)
            scenario = str(plan["scenario"])
            if scenario not in SCENARIOS:
                raise VerificationError(f"unknown scenario: {scenario}")
            if (
                SCENARIOS[scenario].maturity == "experimental"
                and not include_experimental
            ):
                raise VerificationError(
                    "experimental scenario requires explicit opt-in"
                )
            log_path = _safe_child(root / "logs", plan["expected_log_filename"], ".bin")
            receipt_path = _safe_child(
                root / "receipts", plan["expected_receipt_filename"], ".json"
            )
            log_evidence, parsed = _inspect_log(log_path, plan)
            payload_sha256 = str(log_evidence["sha256"])
            if payload_sha256 in seen_payloads:
                raise VerificationError(
                    "duplicate DataFlash payload already used by run "
                    + seen_payloads[payload_sha256]
                )
            receipt = _read_json(receipt_path, maximum_bytes=1024 * 1024)
            acknowledgements = _validate_receipt(
                receipt,
                plan,
                manifest_sha256=manifest_sha256,
                schema=schema,
                log_sha256=payload_sha256,
                log_size=log_path.stat().st_size,
                experiment_root=root,
            )
            if require_pair_commits:
                _require_pair_commit(root, plan, commits_dir=commits_dir)
            onset_sec, onset_absolute, observed_parameters = _observed_injection(
                parsed, plan, receipt, acknowledgements
            )
            if onset_sec is not None:
                minimum_post = float(plan.get("minimum_post_fault_sec", 15.0))
                if float(log_evidence["duration_sec"]) - onset_sec < minimum_post:
                    raise VerificationError(
                        "DataFlash log lacks the required post-fault interval"
                    )
            causal_evidence = _causal_evidence(
                parsed, scenario=scenario, onset_absolute_sec=onset_absolute
            )
            if not causal_evidence["observed"]:
                raise VerificationError(
                    "injection was acknowledged but did not manifest"
                )
            accepted.append(
                _ground_truth_row(
                    plan,
                    manifest_sha256=manifest_sha256,
                    schema=schema,
                    log_evidence=log_evidence,
                    onset_sec=onset_sec,
                    observed_parameters=observed_parameters,
                    causal_evidence=causal_evidence,
                )
            )
            seen_payloads[payload_sha256] = run_id
        except (KeyError, OSError, TypeError, ValueError) as exc:
            rejected.append(
                {
                    "run_id": run_id,
                    "scenario": str(plan.get("scenario", "unknown")),
                    "reason": str(exc),
                }
            )

    ground_truth = {
        "schema": GROUND_TRUTH_SCHEMA,
        "manifest_sha256": manifest_sha256,
        "parameter_schema_sha256": schema.digest,
        "logs": accepted,
    }
    ground_truth_path = root / "ground_truth.json"
    _atomic_json(ground_truth_path, ground_truth)
    receipt = {
        "schema": COLLECTION_SCHEMA,
        "manifest_sha256": manifest_sha256,
        "parameter_schema_sha256": schema.digest,
        "accepted": len(accepted),
        "accepted_run_ids": [row["run_id"] for row in accepted],
        "accepted_payload_sha256": sorted(seen_payloads),
        "rejected": rejected,
        "ground_truth_sha256": sha256_file(ground_truth_path),
        "trainable": bool(accepted),
        "accuracy_claim": "not_evaluated",
    }
    _atomic_json(root / "collection_receipt.json", receipt)
    return receipt
