# DGX Spark GitHub Deployment

The GitHub workflow publishes a native ARM64 **candidate** image to GitHub
Container Registry. Publishing does not qualify the image for scientific or
production use; complete the canary gates in `docs/RUNBOOK_CLUSTER.md` first.

## Publish

1. Open **Actions → Publish DGX Spark candidate image → Run workflow**.
2. Supply an exact 40-character ArduPilot commit.
3. Supply the verified digest of `python:3.12-slim-bookworm` as
   `sha256:<64 lowercase hexadecimal characters>`.
4. Supply a new immutable candidate tag.
5. Record the content digest printed in the workflow summary.

Never deploy by a mutable tag alone. Use the resulting digest:

```bash
docker pull ghcr.io/OWNER/ardupilot-log-diagnosis@sha256:DIGEST
docker run --rm --network none \
  ghcr.io/OWNER/ardupilot-log-diagnosis@sha256:DIGEST \
  python -m synthetic_data cluster preflight
```

For a private package, authenticate using a narrowly scoped read-only token:

```bash
printf '%s' "$GHCR_READ_TOKEN" | docker login ghcr.io -u OWNER --password-stdin
```

Do not pass tokens on command lines, store them in the repository, or mount
them into SITL run containers.
