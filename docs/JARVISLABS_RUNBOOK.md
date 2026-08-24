# JarvisLabs Runbook for Verified ArduPilot Synthetic Data

## Decision

Use JarvisLabs first as an elastic **Linux CPU execution substrate**, not as a
GPU cluster. ArduPilot SITL generation is primarily CPU/process/I/O work, and
the current XGBoost trainer is CPU-bound (`n_jobs=1`, no CUDA device). A GPU
would therefore add cost without a demonstrated speedup today.

The recommended progression is:

1. publish the pinned x86_64 SITL image to GHCR;
2. qualify it on one 4-vCPU JarvisLabs VM;
3. execute exactly one matched sham/intervention pair;
4. verify collection and pair-commit rejection paths;
5. scale pair lineages across CPU VMs only after that canary passes; and
6. benchmark a GPU-enabled trainer on an L4/A30 before considering A100/H100.

## What JarvisLabs contributes

| Project need | JarvisLabs feature | Recommended use |
|---|---|---|
| Linux namespaces and process control | Full VM plus privileged containers | Genuine SITL execution |
| Cheap parallel simulation | CPU VMs from 2 to 32 vCPUs | One pair per worker/container |
| Reproducible image execution | GHCR image through Docker or dstack | Digest-pinned canaries |
| Durable artifacts | `/home`, attached shared filesystem at `/home/jl_fs` | Receipts, BIN logs, ledgers, checkpoints |
| Temporary GPU acceleration | L4/A30/A100/H100 instances | Only measured GPU-compatible training |
| Multi-node private traffic | VPC private interface | Coordinator/worker traffic if needed later |
| Cost control | Per-minute billing, pause/destroy, dstack `max_duration`/`max_price` | Prevent idle spend |

The dashboard and `jl gpus --json` are authoritative for live availability and
pricing. The Jarvis account reports INR billing; the live dstack offer endpoint
returned `8.04` for a 4-vCPU/16-GB CPU VM on 2026-08-25. dstack 0.21.2 compares
that raw provider number for `max_price`, so the canary profile uses an 8.50
cap and a 20-minute maximum (roughly ₹3 at the observed rate). Recheck both
the offer and currency before every campaign.

## Important current limits

- The repository contracts and tests do not prove a live JarvisLabs run.
- The first real sham/intervention pair is still required.
- The current `cluster submit` CLI records dry-run SSH dispatch intent; it is
  not a finished JarvisLabs scheduler.
- Synthetic logs cannot establish real-flight accuracy. They are accepted for
  training only after fidelity, ablation, OOD, calibration, and blinded
  physical-flight confirmation gates.
- Current model training does not use a GPU. Do not rent an A100/H100 for the
  existing trainer.

## 1. Local setup

The JarvisLabs CLI officially supports Linux and macOS; Windows support is
experimental. Prefer Ubuntu/WSL for the control terminal when available.

```bash
uv tool install jarvislabs
jl setup
jl status --json
jl gpus --json
```

Keep `JL_API_KEY` in the local environment or the CLI credential store. Never
place it in this repository. Rotate the previously exposed GitHub token before
using any cloud machine.

## 2. Publish the correct image

The DGX workflow publishes ARM64 and cannot run on JarvisLabs x86 VMs. In
GitHub Actions, run **Publish JarvisLabs SITL candidate image** with:

- an exact 40-character ArduPilot commit;
- the verified `python:3.12-slim-bookworm` manifest digest; and
- a new immutable tag.

Record the final address in this form:

```text
ghcr.io/OWNER/ardupilot-log-diagnosis@sha256:64_HEX_DIGEST
```

The runtime image contains the complete pinned ArduPilot checkout because live
receipts verify Git revision, tree, submodule state, and the compiled binary.

## 3. Lowest-risk first contact: dstack canary

dstack is useful for an ephemeral compatibility test because JarvisLabs is a
native VM backend and dstack supports custom images, privileged mode,
`max_price`, `max_duration`, limited retries, and automatic teardown.

Install dstack once in the control environment:

```bash
python -m pip install "dstack[all]" -U
```

Then run the repository launcher. It creates an isolated local dstack server,
waits for the Jarvis fleet to become `idle`, submits the digest-pinned task,
writes the logs, and always destroys the task/fleet afterward. The API key is
read only from the environment and is never written to the repository:

```bash
export JL_API_KEY='(temporary Jarvis API key)'
python ops/jarvis/run_dstack_canary.py \
  --region india-chennai-01 \
  --results-dir artifacts/jarvis-canary
unset JL_API_KEY
```

PowerShell equivalent:

```powershell
$env:JL_API_KEY = Read-Host "Jarvis API key"
python ops/jarvis/run_dstack_canary.py --region india-chennai-01
Remove-Item Env:JL_API_KEY
```

The launcher fails closed on a missing/failed fleet, a task error, or a
timeout. It does not claim a scientific pair until the task itself emits the
required receipts; this canary currently verifies image, architecture,
namespace, and pinned-source readiness first.

The task refuses a non-x86 image, a dirty/missing ArduPilot checkout, missing
namespace privileges, inadequate capacity, or a price above the pinned live
offer cap. It
retries capacity/interruption events only; scientific or code errors are not
retried.

## 4. Recommended durable path: one CPU VM

Register an SSH key first. Create a 4-vCPU/16-GB VM with the minimum 100-GB VM
disk. Attach a shared filesystem if the outputs must survive instance deletion.

```bash
jl create --vm --cpu --vcpus 4 --ram 16 --storage 100 \
  --name "logdiagnosis-canary" --yes --json
```

Save the returned machine ID. Upload and execute the bootstrap:

```bash
jl upload MACHINE_ID ops/jarvis/bootstrap_vm.sh /home/cloud/bootstrap_vm.sh
jl exec MACHINE_ID --json -- sh -lc \
  'SITL_IMAGE="ghcr.io/OWNER/ardupilot-log-diagnosis@sha256:DIGEST" bash /home/cloud/bootstrap_vm.sh'
```

For a private GHCR package, enter `GHCR_USER` and a narrowly scoped read-only
token in an interactive SSH session; do not put the token in shell history,
CLI arguments, scripts, or task YAML.

Download the canary receipt and stop compute billing:

```bash
jl download MACHINE_ID /home/cloud/logdiagnosis/canary ./jarvis-canary -r
jl pause MACHINE_ID --yes --json
```

If a shared filesystem was attached, the canary will be under
`/home/jl_fs/logdiagnosis/canary` instead. Data under `/home` persists while an
instance is paused; data outside `/home` does not. Paused storage still costs
money. Destroy only after artifacts are copied and verified.

## 5. First genuine pair gate

Do not scale yet. On the qualified VM:

1. capture the complete live parameter inventory from the pinned build;
2. bind it to the exact commit and binary with `synthetic_data schema`;
3. plan one scenario with `--runs-per-scenario 1` (two matched arms);
4. run sham and intervention sequentially inside the privileged, network-none
   container;
5. require both execution receipts before writing the pair-commit pointer;
6. run collection with the `commits/` directory present; and
7. deliberately remove/tamper one pointer in a copy and prove collection
   rejects it.

Use the paths embedded in the Jarvis image:

```text
ARDUPILOT_ROOT=/opt/ardupilot
ARDUPILOT_SITL_BINARY=/opt/ardupilot/build/sitl/bin/arducopter
```

The canary is complete only when the real BIN logs, execution receipts,
pair-commit, collection receipt, image digest, binary hash, source snapshot,
and exact commands are downloaded and hash-verified locally.

## 6. Safe parallelism after the canary

The scientific unit of scheduling is the **lineage pair**, not an individual
flight. Both arms must remain on one worker and become visible together.

```text
campaign
  -> pair 001 -> one worker -> sham then intervention -> one pair commit
  -> pair 002 -> one worker -> sham then intervention -> one pair commit
  -> pair 003 -> one worker -> sham then intervention -> one pair commit
```

Start with two workers, then four. Increase only when failure rate, pair hold
rate, storage throughput, and cost per accepted pair remain stable. Do not
retry missing manifestations; retry only infrastructure interruption or
capacity loss. Shared filesystems favor large files and fewer than roughly
1,000 entries per directory, so shard artifacts by campaign/lineage and stage
intensive temporary I/O under `/home` before copying sealed outputs.

For a future multi-node coordinator, place all VMs in one VPC, use the stable
private `eth1` addresses for worker traffic, keep the public firewall closed
except SSH, and use coordinator-backed fencing rather than local PID locks.

## 7. Training strategy

Run `ops/jarvis/training-cpu.dstack.yml` as the cheap reproducibility baseline.
Before using a GPU, add an explicit candidate configuration for XGBoost CUDA,
bind it to the same frozen split, and compare wall time, cost, macro-F1,
calibration, abstention/FCR, and OOD behavior against the CPU baseline.

Choose the cheapest accelerator that fits:

- L4/A30: first GPU benchmark and ordinary tabular experiments;
- A100: only if data/model size or measured throughput justifies it;
- H100/H200: not justified for the current project.

GPU success means lower measured cost/time without weaker evidence gates. It
does not itself imply better diagnostic accuracy.

## 8. Shutdown checklist

```bash
jl list --json
jl run list --refresh --json
jl pause MACHINE_ID --yes --json
# after verified backup, if the instance is no longer needed:
jl destroy MACHINE_ID --yes --json
```

If a `jl run` session is detached with Ctrl+C or `--no-follow`, automatic
pause/destroy does not occur. Always perform a final account-wide instance
check. Use `jl run logs RUN_ID --tail 50` for bounded monitoring rather than
downloading unbounded logs.

