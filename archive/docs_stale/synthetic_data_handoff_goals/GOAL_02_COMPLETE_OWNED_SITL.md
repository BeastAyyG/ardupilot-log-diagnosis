# Goal 02 — Complete Owned ArduPilot SITL Execution

## Copy/paste prompt

Complete and prove the owned direct-ArduPilot SITL execution path in
`D:/logdiagnosis-codex`. Work only after Goal 01 passes. Use one pinned, clean
ArduPilot checkout and one exact binary/parameter inventory. Keep the simulator
loopback-only and sequential. Produce a real current-schema healthy sham/fault
pair and prove that collection either accepts causally valid logs or quarantines
them fail-closed. Do not substitute fake BIN files, sim_vehicle/MAVProxy/tmux,
or self-reported receipts.

## Existing design to preserve

- Direct ArduCopter binary; `tcpin:127.0.0.1:14550` listener and SITL
  `tcpclient:127.0.0.1:14550` connection.
- Exact binary SHA256, full 40-character Git commit, clean tracked source and
  submodule attestation, one frame-specific parameter schema, fixed home, fixed
  `--start-time`, speedup 1, sysid/component 1, and tested pymavlink 2.4.49.
- Full live parameter inventory/value attestation using exact float32 payload
  equality; MAVLink messages filtered by system and component IDs.
- Bounded arm/takeoff/injection/land/disarm operations.
- Logger remains alive for at least two logger ticks after disarm; log must be
  stable before process-group fencing.
- Logs are staged, fsynced, hashed, size-checked, atomically published, and
  quarantined if receipt publication fails.
- Receipt v4 and experiment manifest v3 are non-trainable until collector checks
  firmware, arm sequence, logger health, parameter trajectory, message coverage,
  manifestation, hashes, and pairing.

## Remaining work

- Run one real end-to-end pair on a platform compatible with the ArduPilot binary
  (Linux/WSL), saving all commands and environment hashes. Confirm the host
  permits unprivileged user/network namespaces and has util-linux `unshare`.

## Local implementation now complete

- Exact command/start-time/loopback/source/submodule/trajectory/receipt tests
  exist, including early exit, unstable logger, SIGKILL escalation, mixed source
  IDs, and receipt-publication rollback into quarantine.
- Native RC input is disabled with `--rc-in-port 0`. Active execution now
  re-execs the complete Python controller and direct ArduPilot child together in
  a fresh Linux user/network namespace. Only `lo` is raised; the live parent and
  child namespace IDs, exact interface list, loopback state, and `unshare`
  binary hash are required in receipt v4 and revalidated by collection.
- Strict baseline → requested → no-reset DataFlash trajectories and the isolated
  `pymavlink==2.4.49` constraints file are implemented.
- These tests prove fail-closed mechanics, not that this Windows host executed
  a real ArduPilot binary. The genuine pair remains mandatory.

## Acceptance criteria

- One genuine healthy/fault pair yields manifest-v3, receipt-v4, DataFlash BIN,
  collection receipt, verified ground truth, and complete hashes.
- Tampering with command, source, parameter file, timing, source ID, log, or
  receipt causes rejection/quarantine before training.
- Repeating the same immutable plan/source produces scenario-equivalent evidence;
  continue to state `bit_exact_replay_claim=false`.
- No network endpoint beyond exact IPv4 loopback is reachable.
