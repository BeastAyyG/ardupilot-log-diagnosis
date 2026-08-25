# Project Context for a New AI

Updated: 2026-08-25

## Objective

This repository has two connected purposes:

1. Diagnose real ArduPilot flight logs with evidence-backed causal analysis.
2. Build a controlled synthetic-data factory that generates genuine ArduPilot
   SITL DataFlash logs for model training and research.

The synthetic-data system must never invent `.BIN` bytes or fabricated derived
features. It launches the real pinned ArduPilot SITL binary, flies controlled
scenarios, injects a registered fault, and preserves the native DataFlash log.
Synthetic data is training evidence. Real physical-flight logs remain the
calibration, evaluation, and final confirmation evidence.

## What one paired run does

The smallest scientifically useful unit is a matched pair:

- a healthy sham/control flight;
- a fault-intervention flight using the same frame, environment, timing, and
  lineage, differing only in the registered intervention.

The runtime performs this chain:

1. Pull an immutable ARM64 container by SHA256 digest.
2. Verify the exact ArduPilot source revision and compiled binary hash.
3. Start an inventory-only SITL process and capture the complete live parameter
   inventory.
4. Create two deterministic, matched run plans bound to the inventory and binary.
5. Launch each flight in a fresh Linux user/network namespace with loopback as
   the only enabled interface.
6. Verify the owned MAVLink heartbeat, system/component identity, frame, startup
   parameters, gyro/accelerometer health, and stationary accelerometer calibration.
7. Enter GUIDED mode, arm, take off, and schedule the intervention using vehicle
   boot time rather than host wall-clock time.
8. Require each parameter write to be acknowledged and independently read back.
9. Land/disarm, stabilize the native DataFlash log, terminate the owned process
   tree, hash the log, and atomically publish the execution receipt.
10. Seal a `pair-commit/v1` pointer only after both pair members succeed. A lone
    surviving member is never eligible for training.
11. Re-collect and validate the plan, log, receipt, parameter changes,
    manifestation, timing, and pair-commit hashes.

The launcher refuses success unless it finds exactly two `.BIN` logs, at least
two execution receipts, and exactly one sealed pair commit.

## Major completed capabilities

- Exact pinned ArduPilot checkout and detached build; no moving branch/tag.
- Direct owned `arducopter` process; no MAVProxy or manual relay dependency.
- Immutable source, binary, command, parameter, dependency, and image bindings.
- Complete live parameter-inventory validation and frame-default merging.
- Loopback endpoint checks and Linux namespace isolation evidence.
- Bounded preflight, calibration, arming, takeoff, injection, landing, shutdown,
  and log-finalization operations.
- Failure quarantine: incomplete or invalid outputs do not become training data.
- Pair-atomic promotion and cryptographic receipt/pair-commit bindings.
- Scientific failure versus transient retry classification.
- Deterministic pair-aware cluster assignment, parallel waves, fencing epochs,
  attempts, reconciliation, assignment ledgers, batch receipts, and seal contracts.
- Collector enforcement of pair commits, causal timing, manifestation, and log
  identity.
- Coverage, fidelity, paired-ablation, calibration, OOD AUROC and
  detection-at-5%-ID-FPR producers/gates, and confirmation-cohort planning.
- GitHub workflows for native ARM64 image publication and a genuine paired SITL
  canary run.

Repository/unit/CI tests prove these software contracts. They do not, by
themselves, prove live hardware execution or an accuracy improvement.

## Immutable inputs at this checkpoint

- Repository: `https://github.com/BeastAyyG/ardupilot-log-diagnosis`
- ArduPilot source commit:
  `1511f27194f1dcc3728270883047bdf022b3fd53`
- Qualified ARM64 base image:
  `ghcr.io/beastayyg/ardupilot-log-diagnosis@sha256:369232ff6a1185a647a08e68a16c9d18e8e8ba5855c0d73ef9c332e398c2d765`
- Current runtime overlay built from main commit
  `6c92d01aa762f5b8a9dd4530d892e816137639de`:
  `ghcr.io/beastayyg/ardupilot-log-diagnosis@sha256:dfa0468382e68806e40e9fb76ee6795cf430f96725e658e62df14f8cbb601480`
- Overlay build evidence:
  `https://github.com/BeastAyyG/ardupilot-log-diagnosis/actions/runs/32850703198`

## Real ARM64 evidence so far

The latest genuine run before this overlay was:

`https://github.com/BeastAyyG/ardupilot-log-diagnosis/actions/runs/32833830111`

Its DataFlash log proves the sham vehicle armed and reached 10.0 m, but the
controller timed out because the pinned inventory suppressed unsolicited
`GLOBAL_POSITION_INT` telemetry. PR #146 merged as
`6c92d01aa762f5b8a9dd4530d892e816137639de`; it explicitly requests the
position stream before takeoff confirmation.

This is meaningful progress, but no genuine two-log completed pair has yet been
proven at the time this file was written.

## Honest completion boundaries

A successful next ARM64 canary proves one quad motor-imbalance sham/intervention
pair can run end to end and produce pair-atomic trainable evidence. It does not
prove:

- model accuracy improvement;
- broad coverage across frames, weather, and fault severities;
- DGX multi-node throughput or coordinator deployment;
- physical-flight realism;
- production safety or independent scientific confirmation.

Accuracy must remain `not demonstrated` until a scaled receipt-verified corpus,
frozen real-only split, source-bound baseline/candidate paired ablation, safety
and calibration gates, OOD evidence, a never-opened blinded physical-flight
confirmation cohort, per-class lineage support, and independent authority
approval all exist.

## Expected one-command operating time

After the software and image are already published and cached, the user-facing
paired workflow is one command/button and usually needs about 5–10 minutes.
A cold image pull may add several minutes. The full development chain—CI, image
rebuild, digest pin, CI again, and the paired run—usually needs 12–20 minutes if
the first live attempt succeeds. A newly observed SITL transition adds another
diagnose/fix/build/pin/run cycle, commonly 10–20 minutes.

The user should not need to intervene in the normal path. Fail-closed gates may
stop the workflow and upload evidence; the automation owner must then diagnose
the exact receipt rather than weakening the gate.
