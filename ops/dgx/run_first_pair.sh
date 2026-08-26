#!/usr/bin/env bash
# Pull and run the pinned DGX Spark image through one verified first pair.
set -Eeuo pipefail

readonly DEFAULT_IMAGE="ghcr.io/beastayyg/ardupilot-log-diagnosis@sha256:285dc9aec7e0e6a9bcea24fb35d1ab10eeba64869bd80859c1cd5ea205ffd79f"
readonly IMAGE="${SITL_IMAGE:-$DEFAULT_IMAGE}"
readonly OUTPUT_DIR="${PAIR_OUTPUT_DIR:-/home/cloud/logdiagnosis/first-pair}"
readonly SCENARIO="${PAIR_SCENARIO:-motor_imbalance}"
readonly FRAME="${PAIR_FRAME:-quad}"
readonly SEED="${PAIR_SEED:-20260823}"
readonly TIMEOUT="${PAIR_TIMEOUT:-120}"
readonly RANDOMIZE_FLAG="${PAIR_RANDOMIZE:-off}"
readonly HOST_UID="$(id -u)"
readonly HOST_GID="$(id -g)"

fail() {
  printf 'first-pair launcher: %s\n' "$1" >&2
  exit 1
}

[[ "$IMAGE" =~ ^ghcr\.io/beastayyg/ardupilot-log-diagnosis@sha256:[0-9a-f]{64}$ ]] \
  || fail "SITL_IMAGE must be the lowercase GHCR image pinned by a 64-hex digest"
[[ "$(uname -m)" == "aarch64" || "$(uname -m)" == "arm64" ]] \
  || fail "this launcher requires an ARM64 DGX Spark node"
command -v docker >/dev/null 2>&1 || fail "docker is not installed"
docker info >/dev/null 2>&1 || fail "docker daemon is unavailable"
[[ "$OUTPUT_DIR" != "/" && -n "$OUTPUT_DIR" ]] || fail "PAIR_OUTPUT_DIR is unsafe"
[[ "$SEED" =~ ^[0-9]+$ ]] || fail "PAIR_SEED must be an integer"
[[ "$TIMEOUT" =~ ^[0-9]+([.][0-9]+)?$ ]] || fail "PAIR_TIMEOUT must be numeric"
[[ "$RANDOMIZE_FLAG" == "on" || "$RANDOMIZE_FLAG" == "off" ]] \
  || fail "PAIR_RANDOMIZE must be on or off"
randomize_line=""
if [[ "$RANDOMIZE_FLAG" == "on" ]]; then
  randomize_line="--randomize"
fi

mkdir -p "$OUTPUT_DIR"
chmod 0777 "$OUTPUT_DIR"
docker pull "$IMAGE"
docker run --rm --privileged --network host \
  --user 0:0 \
  --env HOST_UID="$HOST_UID" \
  --env HOST_GID="$HOST_GID" \
  --env PAIR_SCENARIO="$SCENARIO" \
  --env PAIR_FRAME="$FRAME" \
  --env PAIR_SEED="$SEED" \
  --env PAIR_TIMEOUT="$TIMEOUT" \
  --mount "type=bind,src=$OUTPUT_DIR,dst=/output" \
  "$IMAGE" \
  /bin/sh -c "
    python -m synthetic_data pair \\
      --output-dir /output \\
      --binary /opt/ardupilot/build/sitl/bin/arducopter \\
      --ardupilot-root /opt/ardupilot \\
      --scenario \"\$PAIR_SCENARIO\" \\
      --frame \"\$PAIR_FRAME\" \\
      --seed \"\$PAIR_SEED\" \\
      --timeout \"\$PAIR_TIMEOUT\" \\
      $randomize_line \\
      --confirm-sitl
    status=\$?
    chown -R \"\$HOST_UID:\$HOST_GID\" /output 2>/dev/null || true
    exit \$status
  "

commit_count=$(find "$OUTPUT_DIR/commits" -maxdepth 1 -type f -name '*.json' 2>/dev/null | wc -l)
receipt_count=$(find "$OUTPUT_DIR/receipts" -type f -name '*.json' 2>/dev/null | wc -l)
bin_count=$(find "$OUTPUT_DIR/logs" -maxdepth 1 -type f -iname '*.bin' 2>/dev/null | wc -l)
[[ "$commit_count" -eq 1 ]] || fail "expected exactly one pair commit, found $commit_count"
[[ "$receipt_count" -ge 2 ]] || fail "expected at least two execution receipts, found $receipt_count"
[[ "$bin_count" -eq 2 ]] || fail "expected exactly two SITL BIN logs, found $bin_count"

printf 'first-pair complete: image=%s output=%s commits=%s receipts=%s bin_logs=%s\n' \
  "$IMAGE" "$OUTPUT_DIR" "$commit_count" "$receipt_count" "$bin_count"
