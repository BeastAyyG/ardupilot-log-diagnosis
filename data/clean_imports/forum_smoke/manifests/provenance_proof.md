# Benchmark Data Provenance

- Source folder: `/home/ayyg/ardupilot-log-diagnosis/data/raw_downloads/forum_smoke`
- Generated at (UTC): `2026-02-22T14:52:22.767234+00:00`
- Total `.bin` files scanned: **2**
- Parse-valid `.bin` files (pre-dedupe): **2**
- Unique parse-valid files (SHA256 dedupe): **2**
- Rejected non-log `.bin` files: **0**
- Provisional labeled files (not trainable): **0**
- Unlabeled files (manual review): **0**
- Benchmark-trainable files: **2**

## Policy
- No synthetic/SITL logs used for production benchmark training.
- Provisional labels are excluded from trainable benchmark set.
- Only mapped labels are included in benchmark-ready ground truth.

## Verified Labeled Logs
| File | Raw Label | Mapped Label | Thread URL | Download URL | SHA256 |
|---|---|---|---|---|---|
| `log_0001_compass_interference.bin` | COMPASS_INTERFERENCE | compass_interference | https://discuss.ardupilot.org/t/hexacopter-drifting-away-crash-log-video/26675 | https://discuss.ardupilot.org/uploads/default/original/2X/a/ae37876c5612fc9b39ec4f964e98711c1486eb27.BIN | `b0db91ee3d6a7f0af25dbc4cf97a65e1287a47d8b91fc4973fd5d555f8aab8c0` |
| `log_0002_gps_quality_poor.bin` | GPS_QUALITY_POOR | gps_quality_poor | https://discuss.ardupilot.org/t/3dr-iris-crashed-after-3-successful-waypoints-mission/9269 | https://discuss.ardupilot.org/uploads/default/original/2X/a/adab74336ca2529838e73deed416877ddca176de.BIN | `b9daccd2634d195c9a9312b31e6aa43a5a0a775109a04b6eb57afa61d9c081ef` |

## Provisional Labels
| File | Raw Label | Reason | Thread URL | SHA256 |
|---|---|---|---|---|

## Excluded SITL Sources
- https://github.com/ArduPilot/ardupilot/files/12223207/logs_3.zip
- https://github.com/ArduPilot/ardupilot/files/12223288/logs.zip
- https://github.com/ArduPilot/ardupilot/issues/24445

## Generated Artifacts
- `data/clean_imports/forum_smoke/manifests/source_inventory.csv`
- `data/clean_imports/forum_smoke/manifests/clean_import_manifest.csv`
- `data/clean_imports/forum_smoke/manifests/rejected_manifest.csv`
- `data/clean_imports/forum_smoke/manifests/ground_truth_candidate.json`
- `data/clean_imports/forum_smoke/benchmark_ready/ground_truth.json`
