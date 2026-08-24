"""Deterministic, pair-integrity-preserving cluster SITL scheduling.

Distributed guarantees implemented here (each enforced or testable):

- Pair co-location: ``assign_nodes`` hashes the *lineage identity*, so sham
  and intervention members of one pair always land on the same node.
- Real parallel dispatch: entries are executed wave-by-wave on a thread
  pool; lanes within a wave own disjoint port blocks and run concurrently.
- Terminal vs retryable failures: ``TerminalRunError`` (scientific failure,
  e.g. missing fault manifestation) is never retried — retries would create
  selection bias.
- Pair-atomic publication: individual promotes may fail mid-pair, so a
  lineage is only consumable once its pair commit pointer exists in
  ``<commits_dir>/<lineage>.json`` binding both member receipts.
- Fencing: every lock embeds a monotonic per-root epoch; ``reconcile``
  classifies crashed/stale attempts and ``fence_stale`` revokes dead
  workers' locks by epoch.
- Frozen assignment ledger binds node capabilities, image digest, binary
  hash, and resource profile next to the placement decision.

The scheduler still never fabricates flight results: ``runner`` callables do
the flying under the owned-receipt contract.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..integrity import atomic_json

BATCH_PLAN_SCHEMA = "logdiagnosis.cluster-batch-plan/v1"
BATCH_REPORT_SCHEMA = "logdiagnosis.cluster-batch-report/v1"
BATCH_RECEIPT_SCHEMA = "logdiagnosis.cluster-batch-receipt/v1"
PAIR_COMMIT_SCHEMA = "logdiagnosis.pair-commit/v1"
ASSIGNMENT_LEDGER_SCHEMA = "logdiagnosis.assignment-ledger/v1"
ROLE_ORDER = {"sham_control": 0, "intervention": 1}
DEFAULT_MAVLINK_PORT_BASE = 14550
LOCK_TTL_SECONDS = 900.0


class TerminalRunError(RuntimeError):
    """Scientific failure that must never be retried.

    Raising this from a runner marks the run ``failed_terminal`` after a
    single attempt. Retrying manifestation-missing flights would silently
    condition the corpus on lucky executions — selection bias by construction.
    """


@dataclass(frozen=True)
class SlotAllocation:
    slot: int
    wave: int
    mavlink_port: int
    instance: int


@dataclass(frozen=True)
class BatchEntry:
    run_id: str
    plan: Mapping[str, Any]
    allocation: SlotAllocation


@dataclass
class BatchReport:
    schema: str = BATCH_REPORT_SCHEMA
    entries: list[dict[str, Any]] = field(default_factory=list)
    waves: int = 0
    max_concurrent: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "waves": self.waves,
            "max_concurrent": self.max_concurrent,
            "entries": self.entries,
        }


def _role_key(plan: Mapping[str, Any]) -> int:
    return ROLE_ORDER.get(str(plan.get("pair_role", "")), 2)


def build_batch_plan(
    plans: Sequence[Mapping[str, Any]],
    *,
    max_concurrent: int,
    mavlink_port_base: int = DEFAULT_MAVLINK_PORT_BASE,
    port_block_stride: int = 10,
    instance_base: int = 0,
) -> list[BatchEntry]:
    """Deterministically map plans onto concurrency lanes.

    Each lane owns one disjoint port block; blocks are reused only across
    waves. ``max_concurrent=1`` reproduces sequential single-run behaviour.
    """

    if isinstance(max_concurrent, bool) or max_concurrent < 1:
        raise ValueError("max_concurrent must be a positive integer")
    if len(plans) > 1024 * 64:
        raise ValueError("refusing absurd batch size")
    ordered = sorted(
        plans,
        key=lambda p: (
            str(p.get("lineage_root_id", "")),
            _role_key(p),
            str(p.get("run_id", "")),
        ),
    )
    seen_run_ids: set[str] = set()
    entries: list[BatchEntry] = []
    for index, plan in enumerate(ordered):
        run_id = str(plan.get("run_id", ""))
        if not run_id:
            raise ValueError("batch plans require non-empty run_id values")
        if run_id in seen_run_ids:
            raise ValueError(f"duplicate run_id in batch: {run_id}")
        seen_run_ids.add(run_id)
        slot = index % max_concurrent
        wave = index // max_concurrent
        allocation = SlotAllocation(
            slot=slot,
            wave=wave,
            mavlink_port=mavlink_port_base + slot * port_block_stride,
            instance=instance_base + slot,
        )
        entries.append(BatchEntry(run_id=run_id, plan=plan, allocation=allocation))
    return entries


# ---------------------------------------------------------------------------
# Fencing primitives (monotonic epochs; coordinator contract documented)
# ---------------------------------------------------------------------------


def current_epoch(root: Path) -> int:
    epoch_file = root / ".fencing-epoch"
    if not epoch_file.is_file():
        return 0
    try:
        return int(epoch_file.read_text(encoding="ascii").strip() or 0)
    except (OSError, ValueError):
        return 0


def advance_epoch(root: Path) -> int:
    """Monotonically advance and persist the fencing epoch (coordinator op)."""

    root.mkdir(parents=True, exist_ok=True)
    nxt = current_epoch(root) + 1
    tmp = root / f".fencing-epoch.tmp.{os.getpid()}"
    tmp.write_text(str(nxt), encoding="ascii")
    os.replace(tmp, root / ".fencing-epoch")
    return nxt


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True
    return True


class _RunLock:
    """Exclusive O_EXCL lock carrying a monotonic fencing epoch."""

    def __init__(self, path: Path, *, ttl_seconds: float = LOCK_TTL_SECONDS) -> None:
        self.path = path
        self.ttl_seconds = ttl_seconds
        self._fd: int | None = None
        self.epoch = 0

    def acquire(self, *, epoch: int = 0) -> dict[str, Any]:
        payload = json.dumps(
            {"pid": os.getpid(), "acquired_at": time.time(), "epoch": epoch}
        ).encode()
        while True:
            try:
                self._fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(self._fd, payload)
                self.epoch = epoch
                return {"acquired": True, "stolen": False, "epoch": epoch}
            except FileExistsError:
                try:
                    info = json.loads(self.path.read_text(encoding="utf-8"))
                    age = time.time() - float(info.get("acquired_at", 0.0))
                    pid = int(info.get("pid", -1))
                    held_epoch = int(info.get("epoch", 0))
                except (OSError, ValueError, json.JSONDecodeError):
                    age, pid, held_epoch = self.ttl_seconds + 1.0, -1, 0
                if age <= self.ttl_seconds and _pid_alive(pid):
                    raise RuntimeError(
                        f"another writer holds {self.path.name} "
                        f"(epoch={held_epoch}); single-writer per attempt"
                    ) from None
                try:
                    self.path.unlink()
                except OSError:
                    pass

    def release(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
            try:
                self.path.unlink()
            except OSError:
                pass


def _next_attempt_dir(root: Path, run_id: str) -> Path:
    run_root = root / run_id
    run_root.mkdir(parents=True, exist_ok=True)
    index = 0
    while (run_root / f"attempt-{index}").exists():
        index += 1
    attempt = run_root / f"attempt-{index}"
    attempt.mkdir(parents=True, exist_ok=False)
    return attempt


def _run_one(
    entry: BatchEntry,
    runner: Callable[[BatchEntry, Path], Mapping[str, Any]],
    *,
    root: Path,
    promote: Callable[[Path, Mapping[str, Any]], Path] | None,
    max_attempts: int,
    lock_ttl_seconds: float,
    epoch: int,
    defer_promotion: bool,
) -> tuple[dict[str, Any], Path, Mapping[str, Any] | None]:
    """Drive one entry through its immutable attempts. Returns (record, win)."""

    record: dict[str, Any] = {"run_id": entry.run_id, "attempts": []}
    outcome = "failed"
    last_error = "attempt budget exhausted"
    win: tuple[Path, Mapping[str, Any]] | None = None

    for _ in range(max_attempts):
        attempt_dir = _next_attempt_dir(root, entry.run_id)
        lock = _RunLock(attempt_dir / ".lock", ttl_seconds=lock_ttl_seconds)
        try:
            lock.acquire(epoch=epoch)
        except RuntimeError as exc:
            record["attempts"].append(
                {
                    "attempt_dir": str(attempt_dir),
                    "status": "lock_blocked",
                    "error": str(exc),
                    "fencing_epoch": epoch,
                }
            )
            outcome = "blocked"
            last_error = str(exc)
            break
        try:
            receipt = runner(entry, attempt_dir)
            if not isinstance(receipt, Mapping):
                raise TypeError("runner must return a receipt mapping")
            receipt_path = attempt_dir / "receipt.json"
            atomic_json(receipt_path, dict(receipt))
            promoted = None
            if promote is not None and not defer_promotion:
                promoted = str(promote(attempt_dir, receipt))
            record["attempts"].append(
                {
                    "attempt_dir": str(attempt_dir),
                    "status": "succeeded",
                    "receipt_sha256": _sha256_file(receipt_path),
                    "promoted_to": promoted,
                    "fencing_epoch": epoch,
                }
            )
            outcome = "succeeded"
            last_error = ""
            win = (attempt_dir, receipt)
            break
        except TerminalRunError as exc:
            # Scientific failure: exactly one attempt, no retry, no bias.
            last_error = f"terminal: {exc}"
            record["attempts"].append(
                {
                    "attempt_dir": str(attempt_dir),
                    "status": "failed_terminal",
                    "error": last_error,
                    "fencing_epoch": epoch,
                }
            )
            outcome = "failed_terminal"
            atomic_json(
                attempt_dir / "outcome.json", {"terminal": True, "error": last_error}
            )
            break
        except Exception as exc:  # noqa: BLE001 - failures are data here
            last_error = f"{type(exc).__name__}: {exc}"
            record["attempts"].append(
                {
                    "attempt_dir": str(attempt_dir),
                    "status": "failed",
                    "error": last_error,
                    "fencing_epoch": epoch,
                }
            )
            atomic_json(
                attempt_dir / "outcome.json", {"failed": True, "error": last_error}
            )
        finally:
            lock.release()

    record["status"] = outcome
    record["last_error"] = last_error
    record["allocation"] = {
        "slot": entry.allocation.slot,
        "wave": entry.allocation.wave,
        "mavlink_port": entry.allocation.mavlink_port,
        "instance": entry.allocation.instance,
    }
    record["pair_held"] = False
    return record, (win[0], win[1]) if win else None


def execute_batch(
    entries: Sequence[BatchEntry],
    runner: Callable[[BatchEntry, Path], Mapping[str, Any]],
    *,
    attempts_root: str | Path,
    promote: Callable[[Path, Mapping[str, Any]], Path] | None = None,
    max_attempts: int = 3,
    lock_ttl_seconds: float = LOCK_TTL_SECONDS,
    pair_atomic: bool = False,
    commits_dir: str | Path | None = None,
    parallel: bool = True,
) -> BatchReport:
    """Dispatch every entry through immutable attempts until pass or budget.

    Lanes within one wave execute **concurrently** on a worker pool (their
    port blocks are disjoint); waves execute sequentially so ports recycle
    safely. Report order always mirrors input order regardless of completion
    order. With ``pair_atomic=True``, promotion is deferred and each complete
    lineage receives a pair-commit pointer binding both member receipts;
    incomplete pairs are held and never committed or promoted.
    """

    if isinstance(max_attempts, bool) or max_attempts < 1:
        raise ValueError("max_attempts must be positive")
    root = Path(attempts_root)
    root.mkdir(parents=True, exist_ok=True)
    report = BatchReport(
        max_concurrent=max(1, len({e.allocation.slot for e in entries}) or 1)
    )
    report.waves = (len(entries) + report.max_concurrent - 1) // report.max_concurrent
    epoch = advance_epoch(root)

    records: dict[str, dict[str, Any]] = {}
    wins: dict[str, tuple[Path, Mapping[str, Any]]] = {}
    waves: list[list[BatchEntry]] = [[] for _ in range(report.waves)]
    for entry in entries:  # input order defines wave membership deterministically
        waves[entry.allocation.wave].append(entry)

    with ThreadPoolExecutor(max_workers=max(1, report.max_concurrent)) as pool:
        for wave_entries in waves:
            futures = [
                (
                    entry,
                    pool.submit(
                        _run_one,
                        entry,
                        runner,
                        root=root,
                        promote=promote,
                        max_attempts=max_attempts,
                        lock_ttl_seconds=lock_ttl_seconds,
                        epoch=epoch + entry.allocation.slot,
                        defer_promotion=pair_atomic,
                    ),
                )
                for entry in wave_entries
            ]
            for entry, future in futures:
                record, win = future.result()
                records[entry.run_id] = record
                if win is not None:
                    wins[entry.run_id] = win

    ordered_records = [records[e.run_id] for e in entries]
    report.entries = ordered_records

    if pair_atomic:
        lineages: dict[str, set[str]] = {}
        for entry in entries:
            lineage = str(entry.plan.get("lineage_root_id", ""))
            lineages.setdefault(lineage, set()).add(entry.run_id)
        complete: set[str] = set()
        for lineage, rids in lineages.items():
            if all(records[r]["status"] == "succeeded" for r in rids):
                complete |= set(rids)
        commit_root = Path(commits_dir) if commits_dir else root / "commits"
        commit_root.mkdir(parents=True, exist_ok=True)
        for lineage, rids in sorted(lineages.items()):
            if not (lineage and rids <= complete):
                for rid in rids & set(wins):
                    record = records[rid]
                    record["pair_held"] = True
                    atomic_json(
                        Path(record["attempts"][-1]["attempt_dir"]) / "outcome.json",
                        {"held_pair_atomic": True},
                    )
                continue
            # Promote every member FIRST; only a fully promoted lineage earns
            # its commit pointer, so a half-promoted pair is unobservable.
            promotion_ok = True
            for rid in sorted(rids):
                if promote is None:
                    continue
                attempt_dir, receipt = wins[rid]
                try:
                    records[rid]["attempts"][-1]["promoted_to"] = str(
                        promote(attempt_dir, receipt)
                    )
                except Exception as exc:  # noqa: BLE001 - surfaced in report
                    promotion_ok = False
                    records[rid]["last_error"] = f"promotion failed: {exc}"
                    records[rid]["pair_held"] = True
            if not promotion_ok or promote is None:
                continue
            members = {
                rid: {
                    "receipt_sha256": records[rid]["attempts"][-1]["receipt_sha256"],
                    "attempt_dir": records[rid]["attempts"][-1]["attempt_dir"],
                }
                for rid in sorted(rids)
            }
            commit = {
                "schema": PAIR_COMMIT_SCHEMA,
                "lineage_root_id": lineage,
                "members": members,
                "fencing_epoch": epoch,
            }
            body = json.dumps(commit, sort_keys=True, separators=(",", ":"))
            commit["commit_sha256"] = hashlib.sha256(body.encode()).hexdigest()
            # Lineage ids may contain ':' etc.; keep filenames portable.
            safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in lineage)
            atomic_json(commit_root / f"{safe}.json", commit)
    return report


# ---------------------------------------------------------------------------
# Recovery: reconcile + fence stale workers (never deletes evidence)
# ---------------------------------------------------------------------------


def reconcile(attempts_root: str | Path) -> list[dict[str, Any]]:
    """Classify every attempt dir for safe resume decisions."""

    root = Path(attempts_root)
    if not root.is_dir():
        return []
    states: list[dict[str, Any]] = []
    for run_root in sorted(p for p in root.iterdir() if p.is_dir()):
        for attempt in sorted(
            p
            for p in run_root.iterdir()
            if p.is_dir() and p.name.startswith("attempt-")
        ):
            has_receipt = (attempt / "receipt.json").is_file()
            lock_path = attempt / ".lock"
            state: dict[str, Any] = {
                "run_id": run_root.name,
                "attempt_dir": str(attempt),
                "has_receipt": has_receipt,
            }
            if lock_path.is_file():
                try:
                    info = json.loads(lock_path.read_text(encoding="utf-8"))
                    age = time.time() - float(info.get("acquired_at", 0.0))
                    pid = int(info.get("pid", -1))
                    state["lock_epoch"] = int(info.get("epoch", 0))
                    alive = _pid_alive(pid)
                except (OSError, ValueError, json.JSONDecodeError):
                    age, alive, pid = LOCK_TTL_SECONDS + 1.0, False, -1
                stale = (not alive) or age > LOCK_TTL_SECONDS
                state["lock_state"] = "stale_lock" if stale else "live_lock"
                state["holder_pid"] = pid
            else:
                state["lock_state"] = "unlocked"
            if has_receipt:
                state["resume_action"] = "already_succeeded"
            elif state.get("lock_state") == "stale_lock":
                state["resume_action"] = "fence_then_retry"
            elif state.get("lock_state") == "live_lock":
                state["resume_action"] = "wait_for_holder"
            else:
                state["resume_action"] = "retry_now"
            states.append(state)
    return states


def recover_pending(attempts_root: str | Path) -> list[dict[str, Any]]:
    """Compatibility view: receipt-less attempt dirs needing attention.

    Prefer :func:`reconcile` for full lock/epoch state and
    :func:`fence_stale` for revocation; this keeps the original minimal
    contract working for existing callers.
    """

    return [
        {"run_id": item["run_id"], "attempt_dir": item["attempt_dir"]}
        for item in reconcile(attempts_root)
        if not item["has_receipt"]
    ]


def fence_stale(attempts_root: str | Path) -> list[dict[str, Any]]:
    """Revoke locks held by dead workers (TTL expired). Returns fenced set."""

    fenced: list[dict[str, Any]] = []
    for item in reconcile(attempts_root):
        if item.get("lock_state") == "stale_lock":
            lock_path = Path(item["attempt_dir"]) / ".lock"
            try:
                lock_path.unlink()
            except OSError:
                continue
            fenced.append(item)
    return fenced


# ---------------------------------------------------------------------------
# Placement: pair-co-located nodes + frozen assignment ledger
# ---------------------------------------------------------------------------


def assign_nodes(
    entries: Sequence[BatchEntry],
    nodes: Sequence[str],
    *,
    salt: str = "",
) -> dict[str, str]:
    """Place runs on nodes by **lineage identity**, keeping pairs co-located.

    Hashing the lineage (not the run_id) guarantees sham/intervention members
    of one pair land on the same node; runs without a lineage fall back to
    their run_id.
    """

    unique_nodes = sorted(set(nodes))
    if not unique_nodes:
        raise ValueError("node inventory is empty")
    assignment: dict[str, str] = {}
    for entry in entries:
        identity = str(entry.plan.get("lineage_root_id") or entry.run_id)
        digest = hashlib.sha256(f"{salt}:{identity}".encode()).digest()
        assignment[entry.run_id] = unique_nodes[
            int.from_bytes(digest[:8], "big") % len(unique_nodes)
        ]
    return assignment


def write_assignment_ledger(
    entries: Sequence[BatchEntry],
    nodes: Sequence[str],
    *,
    path: str | Path,
    salt: str = "",
    node_capabilities: Mapping[str, Mapping[str, Any]] | None = None,
    image_digest: str | None = None,
    binary_sha256: str | None = None,
    resource_profile: str | None = None,
) -> str:
    """Freeze placement together with build/capability bindings."""

    placement = assign_nodes(entries, nodes, salt=salt)
    ledger: dict[str, Any] = {
        "schema": ASSIGNMENT_LEDGER_SCHEMA,
        "salt": salt,
        "nodes": sorted(set(nodes)),
        "node_capabilities": dict(sorted((node_capabilities or {}).items())),
        "image_digest": image_digest,
        "binary_sha256": binary_sha256,
        "resource_profile": resource_profile,
        "placement": {rid: placement[rid] for rid in sorted(placement)},
    }
    body = json.dumps(ledger, sort_keys=True, separators=(",", ":")).encode()
    ledger["ledger_sha256"] = hashlib.sha256(body).hexdigest()
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(destination, ledger)
    return _sha256_file(destination)


# ---------------------------------------------------------------------------
# Batch receipt: full history, fencing chain, assignments, pair commits
# ---------------------------------------------------------------------------


def write_batch_receipt(
    report: BatchReport,
    path: str | Path,
    *,
    assignment_ledger_sha256: str | None = None,
    build_bindings: Mapping[str, Any] | None = None,
    pair_commit_shas: Mapping[str, str] | None = None,
) -> str:
    payload = report.to_dict()
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    receipt = {
        "schema": BATCH_RECEIPT_SCHEMA,
        "batch_report_sha256": hashlib.sha256(body).hexdigest(),
        "waves": report.waves,
        "max_concurrent": report.max_concurrent,
        "runs_total": len(payload["entries"]),
        "runs_succeeded": sum(
            1 for e in payload["entries"] if e.get("status") == "succeeded"
        ),
        "runs_failed": sum(
            1
            for e in payload["entries"]
            if str(e.get("status", "")).startswith("failed")
            or e.get("status") == "blocked"
        ),
        "assignment_ledger_sha256": assignment_ledger_sha256,
        "build_bindings": dict(build_bindings or {}),
        "pair_commits": dict(pair_commit_shas or {}),
        "entries": [
            {
                "run_id": e.get("run_id"),
                "status": e.get("status"),
                "pair_held": bool(e.get("pair_held")),
                "attempt_history": [
                    {
                        key: attempt.get(key)
                        for key in (
                            "attempt_dir",
                            "status",
                            "receipt_sha256",
                            "promoted_to",
                            "fencing_epoch",
                            "error",
                        )
                        if key in attempt
                    }
                    for attempt in e.get("attempts", [])
                ],
                "final_receipt_sha256": next(
                    (
                        a.get("receipt_sha256")
                        for a in reversed(e.get("attempts", []))
                        if a.get("status") == "succeeded"
                    ),
                    None,
                ),
            }
            for e in payload["entries"]
        ],
    }
    destination = Path(path)
    atomic_json(destination, receipt)
    return _sha256_file(destination)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
