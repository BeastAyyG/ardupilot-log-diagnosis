#!/usr/bin/env bash
set -Eeuo pipefail

# Prepare and verify a JarvisLabs x86_64 VM for the pinned SITL image.
# Required: SITL_IMAGE=ghcr.io/...@sha256:<64 hex>
# Optional: GHCR_USER and GHCR_READ_TOKEN for a private package.

if [[ ! "${SITL_IMAGE:-}" =~ ^ghcr\.io/.+@sha256:[0-9a-f]{64}$ ]]; then
  echo "SITL_IMAGE must be an immutable GHCR image digest" >&2
  exit 2
fi

if [[ -d /home/jl_fs ]]; then
  JARVIS_RESULTS_ROOT=${JARVIS_RESULTS_ROOT:-/home/jl_fs/logdiagnosis}
else
  JARVIS_RESULTS_ROOT=${JARVIS_RESULTS_ROOT:-/home/cloud/logdiagnosis}
fi

sudo apt-get update
sudo apt-get install -y --no-install-recommends ca-certificates docker.io git
sudo systemctl enable --now docker
mkdir -p "$JARVIS_RESULTS_ROOT/canary" "$JARVIS_RESULTS_ROOT/campaigns"

if [[ -n "${GHCR_READ_TOKEN:-}" ]]; then
  if [[ -z "${GHCR_USER:-}" ]]; then
    echo "GHCR_USER is required when GHCR_READ_TOKEN is set" >&2
    exit 2
  fi
  printf '%s' "$GHCR_READ_TOKEN" | sudo docker login ghcr.io \
    --username "$GHCR_USER" --password-stdin
fi

sudo docker pull "$SITL_IMAGE"
image_arch=$(sudo docker image inspect "$SITL_IMAGE" --format '{{.Architecture}}')
if [[ "$image_arch" != "amd64" ]]; then
  echo "JarvisLabs candidate must be amd64; found $image_arch" >&2
  exit 3
fi

sudo docker run --rm --privileged --network none \
  --mount "type=bind,src=$JARVIS_RESULTS_ROOT/canary,dst=/results" \
  "$SITL_IMAGE" bash -lc '
    set -Eeuo pipefail
    test "$(uname -m)" = x86_64
    test -d "$ARDUPILOT_ROOT/.git"
    git -C "$ARDUPILOT_ROOT" status --porcelain=v1 --untracked-files=no \
      --ignore-submodules=none | (! grep .)
    python -m synthetic_data cluster preflight > /results/preflight.json
    python - <<"PY"
import hashlib
import json
import os
import subprocess
from pathlib import Path

root = Path(os.environ["ARDUPILOT_ROOT"])
binary = Path(os.environ["ARDUPILOT_SITL_BINARY"])
attestation = json.loads((root / "attestation.json").read_text(encoding="utf-8"))
preflight = json.loads(Path("/results/preflight.json").read_text(encoding="utf-8"))
actual_commit = subprocess.check_output(
    ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
).strip()
actual_binary = hashlib.sha256(binary.read_bytes()).hexdigest()
if attestation.get("commit") != actual_commit:
    raise SystemExit("image commit attestation does not match its checkout")
if attestation.get("binary_sha256") != actual_binary:
    raise SystemExit("image binary attestation does not match its binary")
if not preflight.get("user_network_namespace_ok"):
    raise SystemExit("privileged JarvisLabs container lacks user/network namespaces")
receipt = {
    "schema": "logdiagnosis.jarvislabs-canary/v1",
    "image_commit": actual_commit,
    "binary_sha256": actual_binary,
    "preflight": preflight,
}
Path("/results/jarvislabs-canary.json").write_text(
    json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
PY
  '

echo "JarvisLabs canary passed: $JARVIS_RESULTS_ROOT/canary/jarvislabs-canary.json"

