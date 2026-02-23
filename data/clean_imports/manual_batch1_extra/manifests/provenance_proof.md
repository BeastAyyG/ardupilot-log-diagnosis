# Benchmark Data Provenance

- Source folder: `/home/ayyg/ardupilot-log-diagnosis/data/raw_downloads/manual_batch1_extra`
- Generated at (UTC): `2026-02-23T05:12:03.037234+00:00`
- Total `.bin` files scanned: **13**
- Parse-valid `.bin` files (pre-dedupe): **13**
- Unique parse-valid files (SHA256 dedupe): **13**
- Rejected non-log `.bin` files: **0**
- Provisional labeled files (not trainable): **0**
- Unlabeled files (manual review): **0**
- Benchmark-trainable files: **13**

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
| `log_0004_compass_interference.bin` | COMPASS_INTERFERENCE | compass_interference | https://discuss.ardupilot.org/t/hexacopter-drifting-away-crash-log-video/26675 | https://discuss.ardupilot.org/uploads/default/original/2X/a/ae37876c5612fc9b39ec4f964e98711c1486eb27.BIN | `b0db91ee3d6a7f0af25dbc4cf97a65e1287a47d8b91fc4973fd5d555f8aab8c0` |
| `log_0005_compass_interference.bin` | COMPASS_INTERFERENCE | compass_interference | https://discuss.ardupilot.org/t/crash-analysis-strange-flight-behavior/33345 | https://discuss.ardupilot.org/uploads/default/original/3X/0/b/0beedf6d3ca0b7cfee74a05c5236accaf7161563.BIN | `12ee853194f5dd8c499850d524eb385c25e34f36e5d39e41a2db716781576a9c` |
| `log_0006_compass_interference.bin` | COMPASS_INTERFERENCE | compass_interference | https://discuss.ardupilot.org/t/major-ek2-fail-and-big-crash/19650 | https://discuss.ardupilot.org/uploads/default/original/2X/1/1ddc2051ccc5fd63ccf9aee6528a05afacc9e5d3.bin | `16c0fe0044cff1cc632979a2355a9869b1911f445f96766d8bb997a3df653ded` |
| `log_0007_gps_quality_poor.bin` | GPS_QUALITY_POOR | gps_quality_poor | https://discuss.ardupilot.org/t/3dr-iris-crashed-after-3-successful-waypoints-mission/9269 | https://discuss.ardupilot.org/uploads/default/original/2X/a/adab74336ca2529838e73deed416877ddca176de.BIN | `b9daccd2634d195c9a9312b31e6aa43a5a0a775109a04b6eb57afa61d9c081ef` |
| `log_0008_ekf_failure.bin` | EKF_FAILURE | ekf_failure | https://discuss.ardupilot.org/t/stil-fw-4-2-0dev-crashes-the-plane-with-ahrs-ekf3-lane-switch-0-message/77702 | https://www.dropbox.com/s/rxiochh02lb2esi/00000057.BIN?dl=1 | `f121066e7e1c6eb2ce0be294f1ead978e6624eda78126de80d177cac784dd097` |
| `log_0009_ekf_failure.bin` | EKF_FAILURE | ekf_failure | https://discuss.ardupilot.org/t/ekf3-position-still-going-mad-in-beta5-drone-crashed/73859 | https://kopterkraft.com/downloads-static/00000001.BIN | `97845b23ea0075bc6da428f47e9ed4280924a8a9bb8c946ff8835a21eee5192b` |
| `log_0010_ekf_failure.bin` | EKF_FAILURE | ekf_failure | https://discuss.ardupilot.org/t/ekf3-position-still-going-mad-in-beta5-drone-crashed/73859 | https://kopterkraft.com/downloads-static/2021-07-07%2012-06-56.bin | `14f3d252710e50340ce0ccf873d76b405d1cc49e03ddc3826f63d81d3c1f7a3c` |
| `log_0011_power_instability.bin` | POWER_INSTABILITY | power_instability | https://discuss.ardupilot.org/t/large-10kg-payload-drone-crash-on-take-off-please-help/11083 | https://discuss.ardupilot.org/uploads/default/original/2X/8/8f9c107abf27bf95d6872b75b85d1c9a85d9b1cf.bin | `db9fa2016d4646c486498bcff3915ca121f85f4f0509a2e6b8e5f5dbf8d7ee6f` |
| `log_0012_power_instability.bin` | POWER_INSTABILITY | power_instability | https://discuss.ardupilot.org/t/ac-copter-3-7-dev-fell-from-the-sky-crash-log/37800 | https://discuss.ardupilot.org/uploads/default/original/3X/4/d/4dd812963834b929b0b7e09df796084d08cf5f74.BIN | `694da9f46e9da78a4bae2a418de89a4955d971ba36425d6f88c6136e3bd66f2e` |
| `log_0013_power_instability.bin` | POWER_INSTABILITY | power_instability | https://discuss.ardupilot.org/t/loiter-issue-no-mag-data-bad-motor-balance/18364 | https://discuss.ardupilot.org/uploads/default/original/2X/3/31208f6eff64a2551745ff35aca23cdfe9279d4d.bin | `5c454779ece1c78ef0423b23b252d00b17983b2de7c621f8f8706350002e55f1` |

## Provisional Labels
| File | Raw Label | Reason | Thread URL | SHA256 |
|---|---|---|---|---|

## Excluded SITL Sources
- https://github.com/ArduPilot/ardupilot/files/12223207/logs_3.zip
- https://github.com/ArduPilot/ardupilot/files/12223288/logs.zip
- https://github.com/ArduPilot/ardupilot/issues/24445

## Generated Artifacts
- `data/clean_imports/manual_batch1_extra/manifests/source_inventory.csv`
- `data/clean_imports/manual_batch1_extra/manifests/clean_import_manifest.csv`
- `data/clean_imports/manual_batch1_extra/manifests/rejected_manifest.csv`
- `data/clean_imports/manual_batch1_extra/manifests/ground_truth_candidate.json`
- `data/clean_imports/manual_batch1_extra/benchmark_ready/ground_truth.json`
