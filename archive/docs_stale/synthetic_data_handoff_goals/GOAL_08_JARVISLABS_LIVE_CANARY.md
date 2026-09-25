# Goal 08 — JarvisLabs Live Compatibility Canary

## Objective

Publish the exact x86_64 SITL image and prove that one JarvisLabs worker can
run the fail-closed Linux namespace and source/binary attestation checks.

## Inputs

- Repository branch containing `.github/workflows/publish-jarvislabs-image.yml`
- Exact 40-character ArduPilot commit
- Verified manifest digest for `python:3.12-slim-bookworm`
- JarvisLabs API key and registered SSH key
- Rotated GitHub credentials; optional read-only GHCR token if the package is private

## Work

1. Run the GitHub workflow and record its `linux/amd64` image digest.
2. Replace the placeholder in `ops/jarvis/sitl-canary.dstack.yml`.
3. Run `dstack offer -b jarvislabs` and retain the offer/price evidence.
4. Apply the canary task, or create a 4-vCPU Jarvis VM and run
   `ops/jarvis/bootstrap_vm.sh`.
5. Download the canary JSON and logs before pausing/destroying compute.

## Acceptance criteria

- Image reference includes `@sha256:<64 hex>` and reports architecture `amd64`.
- ArduPilot checkout HEAD equals image attestation commit.
- Runtime binary hash equals image attestation binary hash.
- Git tracked/submodule status is clean.
- `user_network_namespace_ok` is true inside the privileged workload.
- Cost, machine/offer ID, region, exact commands, and timestamps are recorded.
- Instance is paused or destroyed and the final `jl list --json` shows no accidental runner.

## Do not claim

This proves environment compatibility only. It does not prove flight execution,
synthetic fidelity, model improvement, or real-world accuracy.

