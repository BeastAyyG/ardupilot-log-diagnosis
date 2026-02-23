# Benchmark Data Provenance

- Source folder: `/home/ayyg/ardupilot-log-diagnosis/data/raw_downloads/forum_batch_lockbox_02`
- Generated at (UTC): `2026-02-22T20:43:41.902165+00:00`
- Total `.bin` files scanned: **11**
- Parse-valid `.bin` files (pre-dedupe): **11**
- Unique parse-valid files (SHA256 dedupe): **11**
- Rejected non-log `.bin` files: **0**
- Provisional labeled files (not trainable): **0**
- Unlabeled files (manual review): **0**
- Benchmark-trainable files: **11**

## Policy
- No synthetic/SITL logs used for production benchmark training.
- Provisional labels are excluded from trainable benchmark set.
- Only mapped labels are included in benchmark-ready ground truth.

## Verified Labeled Logs
| File | Raw Label | Mapped Label | Thread URL | Download URL | SHA256 |
|---|---|---|---|---|---|
| `log_0001_vibration_high.bin` | VIBRATION_HIGH | vibration_high | https://discuss.ardupilot.org/t/crash-help-with-bin-analysis/42329 | https://discuss.ardupilot.org/uploads/default/original/3X/7/6/76e9fe83154fe88ff318770a60b493056acb5ad0.bin | `33c535f6f0edb143bb85909901be52bd73542206e3116ae9ddf22b1c42606cfb` |
| `log_0002_vibration_high.bin` | VIBRATION_HIGH | vibration_high | https://discuss.ardupilot.org/t/copter-crash-althold/60815 | https://discuss.ardupilot.org/uploads/short-url/nXvTLdPIdPX5qTGHEma1Ap4asC5.BIN | `c1bcef192fec48c4eadf1da2a5c62215abc035330b9f56bc5b0e8ecd2a78236f` |
| `log_0003_vibration_high.bin` | VIBRATION_HIGH | vibration_high | https://discuss.ardupilot.org/t/crash-hexacopter-suddenly-crashed-while-auto/83521 | https://www.dropbox.com/s/dunql28hfaatnw6/crash.BIN?dl=1 | `7065a3cd0fbd3c5ce178964dcbb64979fc878d0900fc5f5cb6f30d60d3d9d794` |
| `log_0004_vibration_high.bin` | VIBRATION_HIGH | vibration_high | https://discuss.ardupilot.org/t/is-there-a-vibration-issue-here/15264 | https://discuss.ardupilot.org/uploads/default/original/2X/4/432a250d1ee9eba3884d92235219876f0514a8d1.bin | `1820618f38d81507a1e95ef22f743fbc50817348046d542d9db765ccace2a9d3` |
| `log_0005_vibration_high.bin` | VIBRATION_HIGH | vibration_high | https://discuss.ardupilot.org/t/loiter-mode-climb-drift-and-crash/7594 | https://www.dropbox.com/s/989sciu6lhluz61/Flight%20log.BIN?dl=1 | `a004f350c296ae9f396c8756a95c8b0049913ccc8973c5faf0230eba013ec91d` |
| `log_0006_vibration_high.bin` | VIBRATION_HIGH | vibration_high | https://discuss.ardupilot.org/t/automission-misses-wp2-flyaway-crash/19146 | https://discuss.ardupilot.org/uploads/default/original/2X/1/1a986c229c77716723b88a520e04cacb91ae6803.BIN | `a7290a8733f121989317d53052b0c6eb58b643dd135938f0c3d3614dbb945d04` |
| `log_0007_vibration_high.bin` | VIBRATION_HIGH | vibration_high | https://discuss.ardupilot.org/t/unstable-drone-after-takeoff-crashes/43780 | https://discuss.ardupilot.org/uploads/default/original/3X/4/d/4d5d0263578b30d894308c2e124f0a2cc3cdc1e6.bin | `00afa36e545470c4379352efc54c3dffdd81381ae3bae19890a1cfa1c96dec40` |
| `log_0008_rc_failsafe.bin` | RC_FAILSAFE | rc_failsafe | https://discuss.ardupilot.org/t/radio-failsafe-during-operation/101055 | https://www.dropbox.com/s/zmr1y91j84zsoa3/2023-05-11%2017-08-06%28Testing%29.bin?dl=1 | `b89fc87fea657312f90ca28f92e6108f42bc97cb5c27267df8fc82bdfae690c0` |
| `log_0009_rc_failsafe.bin` | RC_FAILSAFE | rc_failsafe | https://discuss.ardupilot.org/t/radio-failsafe-during-operation/101055 | https://discuss.ardupilot.org/uploads/short-url/sB75zhLsNHbvwByMRs0nPqaLtMl.bin | `af2836cad8f18ca67758f6e45730a2756a37938dfc2f2e2dc6fbb27dca7e5641` |
| `log_0010_rc_failsafe.bin` | RC_FAILSAFE | rc_failsafe | https://discuss.ardupilot.org/t/pixhawk-clone-2-4-8-motors-not-running-in-the-same-speed/93719 | https://discuss.ardupilot.org/uploads/short-url/7Dif4AJuMoDmXUhkloHl8MAlSW4.bin | `0818fe7e5ce3cda47fdf3fef42cb2d02963f354b8b18750fa59edb3d0e035719` |
| `log_0011_rc_failsafe.bin` | RC_FAILSAFE | rc_failsafe | https://discuss.ardupilot.org/t/no-rc-receiver-lockup-between-flight-controller-and-receiver/45811 | https://discuss.ardupilot.org/uploads/default/original/3X/e/2/e2de4f96445c41bb39de162da0afc92f96bc265d.BIN | `8dda19965da2a82b6a0303fbf2bf8f0ef79451f4a87d0b178bb203c8a7376ff2` |

## Provisional Labels
| File | Raw Label | Reason | Thread URL | SHA256 |
|---|---|---|---|---|

## Excluded SITL Sources
- https://github.com/ArduPilot/ardupilot/files/12223207/logs_3.zip
- https://github.com/ArduPilot/ardupilot/files/12223288/logs.zip
- https://github.com/ArduPilot/ardupilot/issues/24445

## Generated Artifacts
- `data/clean_imports/forum_batch_lockbox_02/manifests/source_inventory.csv`
- `data/clean_imports/forum_batch_lockbox_02/manifests/clean_import_manifest.csv`
- `data/clean_imports/forum_batch_lockbox_02/manifests/rejected_manifest.csv`
- `data/clean_imports/forum_batch_lockbox_02/manifests/ground_truth_candidate.json`
- `data/clean_imports/forum_batch_lockbox_02/benchmark_ready/ground_truth.json`
