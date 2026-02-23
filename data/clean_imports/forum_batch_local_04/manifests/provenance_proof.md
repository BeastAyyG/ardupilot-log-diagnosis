# Benchmark Data Provenance

- Source folder: `/home/ayyg/ardupilot-log-diagnosis/data/raw_downloads/forum_batch_local_04`
- Generated at (UTC): `2026-02-22T20:21:41.860110+00:00`
- Total `.bin` files scanned: **1**
- Parse-valid `.bin` files (pre-dedupe): **1**
- Unique parse-valid files (SHA256 dedupe): **1**
- Rejected non-log `.bin` files: **0**
- Provisional labeled files (not trainable): **0**
- Unlabeled files (manual review): **0**
- Benchmark-trainable files: **1**

## Policy
- No synthetic/SITL logs used for production benchmark training.
- Provisional labels are excluded from trainable benchmark set.
- Only mapped labels are included in benchmark-ready ground truth.

## Verified Labeled Logs
| File | Raw Label | Mapped Label | Thread URL | Download URL | SHA256 |
|---|---|---|---|---|---|
| `log_0001_pid_tuning_issue.bin` | PID_TUNING_ISSUE | pid_tuning_issue | https://discuss.ardupilot.org/t/how-to-make-yaw-roll-and-pitch-smoother/64483 | https://www.dropbox.com/s/vbfj9poy4plergf/15-Dec-2020-Crash.BIN?dl=1 | `4dbb9b5fad2e1da945dd1969dc1632091869e3980391666a75106b47015b5e92` |

## Provisional Labels
| File | Raw Label | Reason | Thread URL | SHA256 |
|---|---|---|---|---|

## Excluded SITL Sources
- https://github.com/ArduPilot/ardupilot/files/12223207/logs_3.zip
- https://github.com/ArduPilot/ardupilot/files/12223288/logs.zip
- https://github.com/ArduPilot/ardupilot/issues/24445

## Generated Artifacts
- `data/clean_imports/forum_batch_local_04/manifests/source_inventory.csv`
- `data/clean_imports/forum_batch_local_04/manifests/clean_import_manifest.csv`
- `data/clean_imports/forum_batch_local_04/manifests/rejected_manifest.csv`
- `data/clean_imports/forum_batch_local_04/manifests/ground_truth_candidate.json`
- `data/clean_imports/forum_batch_local_04/benchmark_ready/ground_truth.json`
