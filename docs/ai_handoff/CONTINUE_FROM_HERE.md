# Continue From Here

Updated: 2026-08-26

This file is an execution handoff for another AI. Read
`PROJECT_CONTEXT.md` first.

## Current state

### Latest evidence (authoritative)

- Latest ARM64 pair run:
  `https://github.com/BeastAyyG/ardupilot-log-diagnosis/actions/runs/32901335151`
- Immutable image:
  `sha256:85655cb80e0d1c49d72ee55c0c37c35c99a9bf51698277cf59e6e8e4022573bd`
- The earlier sham run proved heartbeat, inventory, preflight, arming,
  takeoff, flight completion, exact DataFlash selection, logger stabilization,
  and receipt-schema validation.
- Run `32901335151` used the `d01f80c` forced-disarm overlay. Its fault
  DataFlash proves ground contact at 222.8 s at 0.49 m/s and a successful
  forced disarm (`Disarming motors`) at 352.0 s — but no `Land complete`
  event: with `SIM_ENGINE_FAIL=1, SIM_ENGINE_MUL=0.9` the craft rests tilted
  with residual thrust bias, ArduPilot's landing detector never completes,
  and the passive post-LAND wait consumed its whole budget before the cleanup
  forced disarm fired.
- Commit `beeddc7c5bffa7d180dc59219f12a347f182788a` ("Escalate motor-failure
  landing to forced disarm") makes `land_and_disarm` allow a bounded descent
  grace window (half the budget, capped at 60 s), then send the documented
  `param2=21196` forced disarm while budget remains, and log the failure mode
  per phase. Regression tests cover both escalation and natural-disarm paths.
  Do not weaken the completion gate or claim a successful pair yet.

### Local-first policy from this point

Do not merge every runtime experiment. Develop and test candidates before the
final VM/DGX launch:

1. Run unit and contract tests on Windows.
2. Once a Linux Docker runtime exists, build an amd64 candidate and run the
   complete sham/intervention pair locally.
3. Optionally run the ARM64 image under QEMU for packaging/entry-point smoke
   tests; do not treat emulation as ARM performance qualification.
4. Keep fixes on one candidate branch and rebuild candidate images from that
   branch.
5. Merge once the complete pair passes locally.
6. Publish one immutable ARM64 digest and run one final native ARM64/DGX
   confirmation.

Current laptop limitation: the `docker` executable is absent and WSL2 has no
installed Linux distribution. Local container execution therefore requires
Docker Desktop (usually with its WSL2 distribution) or an Ubuntu WSL
installation plus a Docker-compatible engine. Installing either changes the
host and must be explicitly authorized by the user.

Estimated warm local run after setup: 5-10 minutes per pair. First setup and
image acquisition: roughly 20-60 minutes and several GB, depending on network
and whether an image must be built. Native ARM VM/DGX final confirmation:
roughly 5-15 minutes when the image is cached, or 10-30 minutes cold.

- PR #152 and PR #155 are merged.
- Main commit containing exact DataFlash disarm-status acceptance:
  `af46d3f655d011de0a9a6d04d7020672ca9062c1`; candidate canary commit:
  `c4098e29fa64bd5d16916a01f122784b59490790`.
- Overlay build run `32903463261` succeeded; it layers the landing-grace
  escalation from `beeddc7c5bffa7d180dc59219f12a347f182788a` over the
  `sha256:836fc41b58cd541586b8a45b5d5d14b6ce4f31b67dde2108b0e2fb0078bb66be`
  runtime (tag `overlay-beeddc7-landing-grace`).
- New immutable overlay digest:
  `sha256:85655cb80e0d1c49d72ee55c0c37c35c99a9bf51698277cf59e6e8e4022573bd`.
- This branch updates every deployment/test/documentation pin to that digest.
- The next required steps are: validate this branch, run the genuine pair from
  this branch, download the artifact, and verify the evidence.

## Validate the digest-pin branch

Confirm the old overlay digest is absent from deployment surfaces and the new
digest occurs in all five surfaces:

```powershell
rg -n "836fc41b58cd541586b8a45b5d5d14b6ce4f31b67dde2108b0e2fb0078bb66be" `
  ops/dgx/run_first_pair.sh `
  .github/workflows/run-arm64-first-pair.yml `
  docs/DGX_GITHUB_DEPLOYMENT.md `
  tests/test_dgx_launcher.py `
  tests/test_arm64_first_pair_workflow.py

rg -n "85655cb80e0d1c49d72ee55c0c37c35c99a9bf51698277cf59e6e8e4022573bd" `
  ops/dgx/run_first_pair.sh `
  .github/workflows/run-arm64-first-pair.yml `
  docs/DGX_GITHUB_DEPLOYMENT.md `
  tests/test_dgx_launcher.py `
  tests/test_arm64_first_pair_workflow.py
```

Run focused checks:

```powershell
python -m pytest `
  tests/test_dgx_launcher.py `
  tests/test_arm64_first_pair_workflow.py `
  tests/test_runner_loopback.py `
  tests/test_sitl_isolation.py -q

python -m ruff check `
  synthetic_data/runner.py `
  tests/test_runner_loopback.py `
  tests/test_dgx_launcher.py `
  tests/test_arm64_first_pair_workflow.py

git diff --check
```

Stage only the five pin surfaces and these two handoff files. Never stage any
`artifacts/` directory. Commit, push, open a PR to `main`, wait for every CI
check, merge, and record the merge SHA.

## Run the genuine pair

Dispatch from this branch once validation passes (merging the pin PR to
`main` first is still preferred for a final confirmation run):

```powershell
gh workflow run run-arm64-first-pair.yml `
  --repo BeastAyyG/ardupilot-log-diagnosis `
  --ref codex/pin-disarm-status-image `
  -f scenario=motor_imbalance `
  -f frame=quad `
  -f seed=20260840
```

Find and watch the new run:

```powershell
gh run list `
  --repo BeastAyyG/ardupilot-log-diagnosis `
  --workflow run-arm64-first-pair.yml `
  --branch codex/pin-disarm-status-image --limit 1

gh run watch RUN_ID `
  --repo BeastAyyG/ardupilot-log-diagnosis `
  --exit-status
```

Download evidence into a new directory so it cannot mix with previous runs:

```powershell
gh run download RUN_ID `
  --repo BeastAyyG/ardupilot-log-diagnosis `
  -n arm64-first-pair-evidence `
  -D artifacts/arm64-first-pair-final-RUN_ID
```

The artifact is uploaded even when the flight step fails. On failure, inspect
both the failed workflow log and `.failed.json` receipt:

```powershell
gh run view RUN_ID `
  --repo BeastAyyG/ardupilot-log-diagnosis `
  --log-failed
```

Fix only the demonstrated cause, add a regression test, rebuild the overlay,
repin the new digest everywhere, and rerun. Do not bypass the preflight,
namespace, pair-commit, causal-timing, or manifestation gates.

## Required success evidence

Do not claim completion from a green workflow alone. Verify all of these:

- The workflow used the new immutable digest and concluded successfully.
- Exactly two native `.BIN` logs exist.
- At least two successful execution receipts exist; failed receipts are not
  counted as winners.
- Exactly one `commits/*.json` exists with schema
  `logdiagnosis.pair-commit/v1` and exactly two members.
- Independently hash the two on-disk successful receipts and match each hash to
  the pair-commit member entries.
- Both runs share the same lineage/schema/source/binary/environment bindings.
- Each receipt binds ArduPilot commit
  `1511f27194f1dcc3728270883047bdf022b3fd53` and the same binary SHA256.
- Owned heartbeat, live inventory, frame validation, sensor health,
  accelerometer calibration acknowledgement, arm, takeoff, landing/disarm,
  flight completion, process termination, stable log, and clean shutdown are
  all explicitly true.
- Network evidence is loopback-only with no external interfaces.
- Each actual log SHA256 and size matches the receipt.
- The intervention has acknowledged/read-back parameter injection inside the
  registered boot-time window; the sham has no fault exposure.
- Collection passes the registered manifestation and causal timing checks for
  both members and requires the pair commit.

If every item is proven, the correct claim is:

> The GitHub/Docker/ARM64 ArduPilot SITL synthetic-data factory is qualified
> end to end for one paired quad motor-imbalance canary.

Do not expand that sentence into an accuracy, physical-realism, broad-coverage,
or DGX multi-node performance claim without the separate evidence described in
`PROJECT_CONTEXT.md`.

## Files defining the flow

- `.github/workflows/publish-dgx-overlay.yml`
- `.github/workflows/run-arm64-first-pair.yml`
- `ops/dgx/run_first_pair.sh`
- `synthetic_data/first_pair.py`
- `synthetic_data/executor.py`
- `synthetic_data/runner.py`
- `synthetic_data/owned_runner.py`
- `synthetic_data/network_isolation.py`
- `synthetic_data/collector.py`
- `synthetic_data/collector_checks.py`
- `docs/DGX_GITHUB_DEPLOYMENT.md`
- `docs/RUNBOOK_CLUSTER.md`
- `synthetic_data/README.md`
