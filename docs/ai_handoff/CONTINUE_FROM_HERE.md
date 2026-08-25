# Continue From Here

Updated: 2026-08-26

This file is an execution handoff for another AI. Read
`PROJECT_CONTEXT.md` first.

## Current state

### Latest evidence (authoritative)

- Latest ARM64 pair run:
  `https://github.com/BeastAyyG/ardupilot-log-diagnosis/actions/runs/32896227226`
- Immutable image:
  `sha256:8617e76d2d1ac317b1d2c638ae33b6864ba126d7872838e8d8e18ab77c65f310`
- The earlier sham run proved heartbeat, inventory, preflight, arming,
  takeoff, flight completion, exact DataFlash selection, logger stabilization,
  and receipt-schema validation.
- The latest retry used the disarm-aware image, but the fault arm selected
  `SIM_ENGINE_MUL=0.35`, hit the ground at about 8 m/s, and remained armed;
  its DataFlash contained no `Disarming motors` event. The observer therefore
  failed closed correctly. The canary range is now bounded to 0.7/0.8/0.9;
  do not weaken the completion gate or claim a successful pair yet.

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
- New ARM64 overlay build run `32897590440` succeeded.
- New immutable overlay digest:
  `sha256:8617e76d2d1ac317b1d2c638ae33b6864ba126d7872838e8d8e18ab77c65f310`.
- This branch updates every deployment/test/documentation pin to that digest.
- The next required steps are: validate this branch, merge its pin PR, run the
  genuine pair from main, download the artifact, and verify the evidence.

## Validate the digest-pin branch

Confirm the old overlay digest is absent from deployment surfaces and the new
digest occurs in all five surfaces:

```powershell
rg -n "15130516e46ce104c8dae1d1678fd56d3f34c36fd2f853d68da9a8995c58b4af" `
  ops/dgx/run_first_pair.sh `
  .github/workflows/run-arm64-first-pair.yml `
  docs/DGX_GITHUB_DEPLOYMENT.md `
  tests/test_dgx_launcher.py `
  tests/test_arm64_first_pair_workflow.py

rg -n "8617e76d2d1ac317b1d2c638ae33b6864ba126d7872838e8d8e18ab77c65f310" `
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

Only after the pin PR is merged to main:

```powershell
gh workflow run run-arm64-first-pair.yml `
  --repo BeastAyyG/ardupilot-log-diagnosis `
  --ref main `
  -f scenario=motor_imbalance `
  -f frame=quad `
  -f seed=20260840
```

Find and watch the new run:

```powershell
gh run list `
  --repo BeastAyyG/ardupilot-log-diagnosis `
  --workflow run-arm64-first-pair.yml `
  --branch main --limit 1

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
