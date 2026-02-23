# Benchmark Data Provenance

- Source folder: `/home/ayyg/ardupilot-log-diagnosis/data/raw_downloads/forum_batch_local_01`
- Generated at (UTC): `2026-02-22T19:01:02.589466+00:00`
- Total `.bin` files scanned: **12**
- Parse-valid `.bin` files (pre-dedupe): **12**
- Unique parse-valid files (SHA256 dedupe): **12**
- Rejected non-log `.bin` files: **0**
- Provisional labeled files (not trainable): **0**
- Unlabeled files (manual review): **0**
- Benchmark-trainable files: **12**

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
| `log_0008_compass_interference.bin` | COMPASS_INTERFERENCE | compass_interference | https://discuss.ardupilot.org/t/hexacopter-drifting-away-crash-log-video/26675 | https://discuss.ardupilot.org/uploads/default/original/2X/a/ae37876c5612fc9b39ec4f964e98711c1486eb27.BIN | `b0db91ee3d6a7f0af25dbc4cf97a65e1287a47d8b91fc4973fd5d555f8aab8c0` |
| `log_0009_compass_interference.bin` | COMPASS_INTERFERENCE | compass_interference | https://discuss.ardupilot.org/t/crash-analysis-strange-flight-behavior/33345 | https://discuss.ardupilot.org/uploads/default/original/3X/0/b/0beedf6d3ca0b7cfee74a05c5236accaf7161563.BIN | `12ee853194f5dd8c499850d524eb385c25e34f36e5d39e41a2db716781576a9c` |
| `log_0010_compass_interference.bin` | COMPASS_INTERFERENCE | compass_interference | https://discuss.ardupilot.org/t/major-ek2-fail-and-big-crash/19650 | https://discuss.ardupilot.org/uploads/default/original/2X/1/1ddc2051ccc5fd63ccf9aee6528a05afacc9e5d3.bin | `16c0fe0044cff1cc632979a2355a9869b1911f445f96766d8bb997a3df653ded` |
| `log_0011_compass_interference.bin` | COMPASS_INTERFERENCE | compass_interference | https://discuss.ardupilot.org/t/copter-3-4-rc5-possible-imu-or-compass-issues/11636 | https://discuss.ardupilot.org/uploads/default/original/2X/8/87ff98701613197d40b5d92732c7cff4fee0e310.BIN | `d74079b8cc2b19be02a15e8a2275b28279b50f3bc61056468ca6da3d1d5714e2` |
| `log_0012_gps_quality_poor.bin` | GPS_QUALITY_POOR | gps_quality_poor | https://discuss.ardupilot.org/t/3dr-iris-crashed-after-3-successful-waypoints-mission/9269 | https://discuss.ardupilot.org/uploads/default/original/2X/a/adab74336ca2529838e73deed416877ddca176de.BIN | `b9daccd2634d195c9a9312b31e6aa43a5a0a775109a04b6eb57afa61d9c081ef` |

## Provisional Labels
| File | Raw Label | Reason | Thread URL | SHA256 |
|---|---|---|---|---|

## Excluded SITL Sources
- https://github.com/ArduPilot/ardupilot/files/12223207/logs_3.zip
- https://github.com/ArduPilot/ardupilot/files/12223288/logs.zip
- https://github.com/ArduPilot/ardupilot/issues/24445

## Generated Artifacts
- `data/clean_imports/forum_batch_local_01/manifests/source_inventory.csv`
- `data/clean_imports/forum_batch_local_01/manifests/clean_import_manifest.csv`
- `data/clean_imports/forum_batch_local_01/manifests/rejected_manifest.csv`
- `data/clean_imports/forum_batch_local_01/manifests/ground_truth_candidate.json`
- `data/clean_imports/forum_batch_local_01/benchmark_ready/ground_truth.json`
