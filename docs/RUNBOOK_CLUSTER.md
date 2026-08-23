# Cluster Runtime — Operator & Recovery Runbook

Scope: parallel owned-SITL execution from a laptop or a DGX node. This
runbook describes only what the code in `synthetic_data/cluster/` enforces
today; anything requiring hardware you do not have is marked **BLOCKED
(hardware)**.

## 1. Preflight (every session, both profiles)

```powershell
python - <<'PY'
from synthetic_data.cluster.topology import probe_host, recommend_topology
probe = probe_host()
print(probe)
print(recommend_topology(probe, profile="laptop"))   # or "dgx"
PY
```

Gate on these fields before scheduling:

| Field | Pass condition | If failed |
|---|---|---|
| `arch_supported` | amd64/arm64 | do not fly; wrong binary class |
| `user_network_namespace_ok` | `true` (Linux only) | fall back to lanes=1 or run inside container |
| `capacity_ok` | `true` | reduce lanes or free RAM |

On Windows hosts the namespace check reports an explicit failure reason —
that is correct behaviour, not a bug. WSL2 counts as Linux.

## 2. Ports, storage and layout

- One port block per lane: MAVLink `14550 + 10*slot`, sim ports
  `9002/9003 + 10*slot`, irlock `9005 + 10*slot`, base `5760 + 10*slot`.
  Blocks are disjoint within a wave and recycled only across waves
  (`build_batch_plan` guarantees this).
- Attempts live under one root: `<attempts_root>/<run_id>/attempt-N/`.
  Directories are allocated by monotonic scan and are **never rewritten**.
- Canonical outputs are promoted out of the winning attempt via the
  `promote` callback; losing attempts stay for audit with `outcome.json`.

## 3. Scheduling with pair integrity

Sorting is `(lineage_root_id, role, run_id)` so sham/intervention members of
one lineage are always adjacent regardless of worker count. Rules:

1. Put paired runs in the same batch call — never split a lineage across
   batches.
2. Keep `max_concurrent=1` unless `user_network_namespace_ok` is true.
3. Determinism claim covers *assignment* only: re-running the same plan set
   yields identical slot/wave/port maps. Flight content may differ;
   `bit_exact_replay_claim=false` always.

## 4. Retry policy (fail-closed)

- Up to `max_attempts` (default 3) immutable attempts per run.
- A failed attempt keeps its directory plus `outcome.json` error note; a
  crashed attempt's partial files are evidence, not garbage.
- After budget exhaustion the run is reported `"failed"` and nothing is
  promoted. Never raise `max_attempts` mid-batch to rescue a failing arm —
  that converts a hardware signal into tuning noise.

### 4a. Pair-atomic promotion

Pass `pair_atomic=True` to `execute_batch` for cluster runs: promotion is
deferred until the whole batch lands, and a lineage's artifacts are promoted
only when **both** sham and intervention arms succeeded. A lone surviving arm
is reported with `pair_held=true` and an `outcome.json`
`{"held_pair_atomic": true}` marker instead of entering training. A fault
without its sham is not evidence; it is a quarantine candidate.

### 4b. Crash recovery across restarts

After any killed/aborted batch run:

```powershell
python -c "from synthetic_data.cluster import recover_pending; print(recover_pending('<attempts_root>'))"
```

Receipt-less attempt dirs are the crash inventory. Re-running the same batch
continues numbering monotonically (`attempt-1`, `attempt-2`, …) and never
rewrites crash evidence.

## 4c. Deterministic node assignment (DGX fleets)

```powershell
python -c "from synthetic_data.cluster import assign_nodes, build_batch_plan; ..."
```

`assign_nodes(entries, nodes, salt="rack7")` is a pure hash of
`(salt, run_id)`: identical across restarts and plan reordering, balanced by
construction, and isolatable per fleet/rack via the salt.

## 4d. Batch receipts

`write_batch_receipt(report, path)` emits
`logdiagnosis.cluster-batch-receipt/v1` binding the canonical batch-report
hash plus each run's winning receipt SHA256 — feed this into your monitoring
pipeline as the single acceptance artifact per batch.

## 5. Distributed claims and fencing

- Single-writer per attempt: O_EXCL `.lock` containing `{pid,
  acquired_at}`. A second writer fails with `single-writer per run`.
- Stale-lock theft requires **both** TTL expiry (`LOCK_TTL_SECONDS`, 900 s)
  and/or a dead PID. Manual override: delete the lock only after confirming
  via process table that no runner owns it, then record the decision in the
  batch report notes.
- Cross-host worktree fencing stays under the repository harness authority
  (`.harness/session.json`, ADR-324/325). The scheduler never claims
  worktrees; it claims only its own attempts root.

## 6. Receipts and provenance chain

Every successful attempt writes `receipt.json` (atomic) whose SHA256 lands
in the batch report. Downstream trust order:

1. Batch report entry → receipt sha256 → receipt v4 → manifest v3 hash →
   parameter schema digest → binary SHA256 / commit attestation.
2. Collection (`collect`) independently re-verifies command, trajectory,
   logger health, hashes, pairing. Container builds must emit
   `/attestation.json` matching the schema binding exactly.

## 7. Failure-injection suite (CI gate)

Run before any cluster rollout:

```powershell
python -m pytest tests/test_cluster_scheduler.py tests/test_cluster_topology.py -q
```

Covered injections: SIGKILL-style crash mid-attempt (retention + retry),
retry exhaustion (no publication), live-lock contention (blocked status),
stale-lock theft after TTL, duplicate run_id refusal, port-block disjointness
across waves, assignment determinism under input reversal.

## 8. Recovery recipes

| Symptom | Action |
|---|---|
| Run stuck `lock_blocked` | Inspect holder PID in `.lock`; kill or wait; rerun batch (attempt scan continues monotonically). |
| Repeated failures on one lane only | Suspect that lane's port block (leftover socket). Change `mavlink_port_base` by ≥ block stride and retry once; if it follows the plan, the plan/binary is at fault, not the port. |
| Attempt dirs ballooning | Safe to archive `attempt-*` older than the last succeeded index for each run; never delete the winning attempt before promotion verified. |
| Host probe fails after kernel update | Re-run `unshare -Urn true`; new kernels sometimes disable unprivileged userns (`sysctl kernel.unprivileged_userns_clone`). |
| DGX image drift suspicion | Compare `/attestation.json` inside the container against the pinned schema digest; mismatch = quarantine everything flown since last good attestation. |

## 9. Explicitly BLOCKED (hardware)

- Actually flying the genuine healthy/fault pair (Goal 02 tail).
- Building/pushing the ARM64 image to a real registry (digest pin above must
  be filled from YOUR verified mirror).
- Any confirmation-cohort acquisition or accuracy statement.
