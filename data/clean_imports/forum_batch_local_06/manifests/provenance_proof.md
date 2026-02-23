# Benchmark Data Provenance

- Source folder: `/home/ayyg/ardupilot-log-diagnosis/data/raw_downloads/forum_batch_local_06`
- Generated at (UTC): `2026-02-23T06:07:27.796115+00:00`
- Total `.bin` files scanned: **0**
- Parse-valid `.bin` files (pre-dedupe): **0**
- Unique parse-valid files (SHA256 dedupe): **0**
- Rejected non-log `.bin` files: **0**
- Provisional labeled files (not trainable): **0**
- Unlabeled files (manual review): **0**
- Benchmark-trainable files: **0**

## Policy
- No synthetic/SITL logs used for production benchmark training.
- Provisional labels are excluded from trainable benchmark set.
- Only mapped labels are included in benchmark-ready ground truth.

## Verified Labeled Logs
| File | Raw Label | Mapped Label | Thread URL | Download URL | SHA256 |
|---|---|---|---|---|---|

## Provisional Labels
| File | Raw Label | Reason | Thread URL | SHA256 |
|---|---|---|---|---|

## Excluded SITL Sources
- https://github.com/ArduPilot/ardupilot/files/12223207/logs_3.zip
- https://github.com/ArduPilot/ardupilot/files/12223288/logs.zip
- https://github.com/ArduPilot/ardupilot/issues/24445

## Generated Artifacts
- `data/clean_imports/forum_batch_local_06/manifests/source_inventory.csv`
- `data/clean_imports/forum_batch_local_06/manifests/clean_import_manifest.csv`
- `data/clean_imports/forum_batch_local_06/manifests/rejected_manifest.csv`
- `data/clean_imports/forum_batch_local_06/manifests/ground_truth_candidate.json`
- `data/clean_imports/forum_batch_local_06/benchmark_ready/ground_truth.json`
