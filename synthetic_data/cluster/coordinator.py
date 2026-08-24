"""Cross-node coordinator: freeze, submit, status, reconcile, seal.

The coordinator owns the only mutable coordination state (assignment ledger,
pair-scoped claims with fencing epochs, sealed batch receipts). Workers are
fenced by monotonic epochs; dispatch is pluggable — the SSH transport emits
the exact remote command, and a dry-run/local transport records it for tests
and for the operator's audit log.

Sealing is fail-closed: a batch seals only when every lineage in the frozen
campaign has a pair-commit pointer and no claim is still leased.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..integrity import atomic_json
from .scheduler import (
    advance_epoch,
    assign_nodes,
    build_batch_plan,
    current_epoch,
    fence_stale,
    reconcile,
    write_assignment_ledger,
    write_batch_receipt,
    _sha256_file,
)

CAMPAIGN_SCHEMA = "logdiagnosis.cluster-campaign/v1"
CLAIM_SCHEMA = "logdiagnosis.cluster-claim/v1"
SEALED_SCHEMA = "logdiagnosis.cluster-sealed-batch/v1"
DEFAULT_LEASE_SECONDS = 3600.0


@dataclass
class SSHTransport:
    """Emit (or execute) the remote worker command for one attempt."""

    user_host_prefix: str = ""
    dry_run: bool = True
    dispatched: list[dict[str, Any]] = field(default_factory=list)

    def dispatch(self, node: str, task_path_remote: str) -> dict[str, Any]:
        remote = f"{self.user_host_prefix}{node}" if self.user_host_prefix else node
        argv = [
            "ssh",
            remote,
            "python3",
            "-m",
            "synthetic_data.cluster.worker",
            "--task-json",
            task_path_remote,
        ]
        record = {"node": node, "argv": argv, "task": task_path_remote}
        self.dispatched.append(record)
        if not self.dry_run:
            import subprocess

            result = subprocess.run(argv, check=False)
            record["returncode"] = result.returncode
        return record


class ClusterCoordinator:
    def __init__(
        self,
        state_dir: str | Path,
        *,
        attempts_root: str | Path,
        commits_dir: str | Path,
        transport: SSHTransport | None = None,
        lease_seconds: float = DEFAULT_LEASE_SECONDS,
    ) -> None:
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.attempts_root = Path(attempts_root)
        self.commits_dir = Path(commits_dir)
        self.transport = transport or SSHTransport()
        self.lease_seconds = lease_seconds

    # -- freeze -------------------------------------------------------------
    def freeze(
        self,
        campaign_id: str,
        plans: Sequence[Mapping[str, Any]],
        nodes: Sequence[str],
        *,
        salt: str = "",
        image_digest: str | None = None,
        binary_sha256: str | None = None,
        resource_profile: str | None = None,
        max_concurrent: int = 1,
    ) -> dict[str, Any]:
        if not campaign_id.replace("-", "").replace("_", "").isalnum():
            raise ValueError("campaign id must be alphanumeric/-/_")
        entries = build_batch_plan(plans, max_concurrent=max_concurrent)
        # Placement lives inside the frozen ledger; submit() reads it back
        # from disk so the frozen file is the single source of truth.
        assign_nodes(entries, nodes, salt=salt)
        ledger_sha = write_assignment_ledger(
            entries,
            nodes,
            path=self.state_dir / f"{campaign_id}.assignment.json",
            salt=salt,
            image_digest=image_digest,
            binary_sha256=binary_sha256,
            resource_profile=resource_profile,
        )
        manifest = {
            "schema": CAMPAIGN_SCHEMA,
            "campaign_id": campaign_id,
            "nodes": sorted(set(nodes)),
            "salt": salt,
            "assignment_ledger_sha256": ledger_sha,
            "runs_total": len(entries),
            "lineages": sorted({str(p["lineage_root_id"]) for p in plans}),
            "runs_index": {
                str(p["run_id"]): {
                    "lineage_root_id": str(p["lineage_root_id"]),
                    "pair_role": str(p.get("pair_role") or p.get("role", "")),
                }
                for p in plans
            },
            "frozen_at_epoch": current_epoch(self.state_dir)
            or advance_epoch(self.state_dir),
        }
        atomic_json(self.state_dir / f"{campaign_id}.campaign.json", manifest)
        return manifest

    def _load_campaign(self, campaign_id: str) -> dict[str, Any]:
        path = self.state_dir / f"{campaign_id}.campaign.json"
        if not path.is_file():
            raise ValueError(f"campaign {campaign_id} is not frozen")
        return json.loads(path.read_text(encoding="utf-8"))

    # -- submit -------------------------------------------------------------
    def submit(
        self,
        campaign_id: str,
        *,
        pairs: Sequence[str] | None = None,
        task_builder: Callable[[str, str, int], Mapping[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Issue pair-scoped claims and dispatch workers over the transport.

        ``task_builder(node, run_id, epoch)`` materialises the remote task
        file; the default records intent only (dry-run planning).
        """

        manifest = self._load_campaign(campaign_id)
        ledger = json.loads(
            (self.state_dir / f"{campaign_id}.assignment.json").read_text(
                encoding="utf-8"
            )
        )
        placement = ledger["placement"]
        wanted_lineages = set(pairs or manifest["lineages"])
        epoch = advance_epoch(self.state_dir)
        issued: list[dict[str, Any]] = []
        claims_dir = self.state_dir / "claims"
        claims_dir.mkdir(parents=True, exist_ok=True)
        runs_index = manifest["runs_index"]
        for lineage in sorted(wanted_lineages):
            member_runs = sorted(
                rid
                for rid, meta in runs_index.items()
                if meta.get("lineage_root_id") == lineage
            )
            if not member_runs:
                continue
            node = placement[member_runs[0]]
            claim = {
                "schema": CLAIM_SCHEMA,
                "campaign_id": campaign_id,
                "lineage_root_id": lineage,
                "node": node,
                "members": member_runs,
                "fencing_epoch": epoch,
                "leased_until": time.time() + self.lease_seconds,
            }
            safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in lineage)
            atomic_json(claims_dir / f"{safe}.json", claim)
            task_path_remote = f"/srv/logdiagnosis/coordinator/tasks/{safe}.task.json"
            if task_builder is not None:
                task_builder(node, member_runs[0], epoch)
            issued.append(self.transport.dispatch(node, task_path_remote))
        return issued

    # -- status -------------------------------------------------------------
    def status(self) -> dict[str, Any]:
        claims_dir = self.state_dir / "claims"
        now = time.time()
        claims = []
        for path in sorted(claims_dir.glob("*.json")) if claims_dir.is_dir() else []:
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["lease_expired"] = now > float(payload.get("leased_until", 0))
            claims.append(payload)
        pending = reconcile(self.attempts_root)
        committed = []
        if self.commits_dir.is_dir():
            for p in sorted(self.commits_dir.glob("*.json")):
                try:
                    payload = json.loads(p.read_text(encoding="utf-8"))
                    committed.append(str(payload.get("lineage_root_id", p.stem)))
                except (OSError, json.JSONDecodeError):
                    committed.append(p.stem)
        return {
            "epoch": current_epoch(self.state_dir),
            "claims": claims,
            "pending_attempts": pending,
            "committed_lineages": sorted(committed),
        }

    # -- reconcile ----------------------------------------------------------
    def reconcile(self) -> dict[str, Any]:
        fenced = fence_stale(self.attempts_root)
        status = self.status()
        return {"fenced": fenced, **status}

    # -- seal ---------------------------------------------------------------
    def seal(
        self,
        campaign_id: str,
        report: Any,
        *,
        output_path: str | Path,
    ) -> str:
        """Seal the batch: refuse unless every lineage committed & leases free."""

        manifest = self._load_campaign(campaign_id)
        status = self.status()
        live_leases = [c for c in status["claims"] if not c.get("lease_expired", True)]
        if live_leases:
            raise ValueError(f"cannot seal: {len(live_leases)} claim(s) still leased")
        committed = set(status["committed_lineages"])
        missing = sorted(set(manifest["lineages"]) - committed)
        if missing:
            raise ValueError(
                f"cannot seal: lineages without pair-commit pointers: {missing}"
            )
        commit_shas = {
            p.stem: _sha256_file(p) for p in sorted(self.commits_dir.glob("*.json"))
        }
        receipt_sha = write_batch_receipt(
            report,
            output_path,
            assignment_ledger_sha256=manifest["assignment_ledger_sha256"],
            build_bindings={
                "image_digest": manifest.get("image_digest"),
                "binary_sha256": manifest.get("binary_sha256"),
            },
            pair_commit_shas=commit_shas,
        )
        sealed = {
            "schema": SEALED_SCHEMA,
            "campaign_id": campaign_id,
            "batch_receipt_sha256": receipt_sha,
            "committed_lineages": sorted(committed),
            "sealed_at_epoch": current_epoch(self.state_dir),
        }
        atomic_json(self.state_dir / f"{campaign_id}.sealed.json", sealed)
        return receipt_sha
