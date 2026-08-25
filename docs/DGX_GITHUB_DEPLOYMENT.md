# DGX Spark GitHub Deployment

The GitHub workflow publishes a native ARM64 **candidate** image to GitHub
Container Registry. Publishing does not qualify the image for scientific or
production use; complete the canary gates in `docs/RUNBOOK_CLUSTER.md` first.

The currently published ARM64 candidate is:

```text
ghcr.io/beastayyg/ardupilot-log-diagnosis@sha256:47f257c56959959be9a2951d85b8ecb39fb7a958cf24c7e21daa62413957be7b
```

## Publish

1. Open **Actions → Publish DGX Spark candidate image → Run workflow**.
2. Supply an exact 40-character ArduPilot commit.
3. Supply the verified digest of `python:3.12-slim-bookworm` as
   `sha256:<64 lowercase hexadecimal characters>`.
4. Supply a new immutable candidate tag.
5. Record the content digest printed in the workflow summary.

Never deploy by a mutable tag alone. Use the resulting digest:

```bash
docker pull ghcr.io/beastayyg/ardupilot-log-diagnosis@sha256:47f257c56959959be9a2951d85b8ecb39fb7a958cf24c7e21daa62413957be7b
docker run --rm --network none \
  ghcr.io/beastayyg/ardupilot-log-diagnosis@sha256:47f257c56959959be9a2951d85b8ecb39fb7a958cf24c7e21daa62413957be7b \
  python -m synthetic_data cluster preflight
```

## One-command first pair

After Docker and privileged containers are enabled on the DGX node, run:

```bash
PAIR_OUTPUT_DIR=/home/cloud/logdiagnosis/first-pair \
  bash ops/dgx/run_first_pair.sh
```

The launcher pulls the immutable ARM64 image, captures live parameters,
executes the sham and intervention arms, and refuses to report success unless
exactly two BIN logs, both execution receipts, and one sealed pair commit are
present. It preserves all failure evidence for inspection.

For a private package, authenticate using a narrowly scoped read-only token:

```bash
printf '%s' "$GHCR_READ_TOKEN" | docker login ghcr.io -u OWNER --password-stdin
```

Do not pass tokens on command lines, store them in the repository, or mount
them into SITL run containers.
