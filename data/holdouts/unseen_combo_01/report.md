# Unseen Holdout Report

- Output root: `data/holdouts/unseen_combo_01`
- Exclude batches: `forum_batch_local_01, forum_batch_local_02, forum_batch_local_03`
- Candidate batches: `forum_batch_local_04, forum_batch_local_05, flight_logs_dataset_2026-02-22`
- Selected unseen logs: **2**
- Skipped due to overlap: **10**
- Skipped due to missing mapping/files: **0**

## Label Distribution

| Label | Count |
|---|---:|
| compass_interference | 1 |
| vibration_high | 1 |

## Origin Batch Distribution

| Batch | Count |
|---|---:|
| flight_logs_dataset_2026-02-22 | 2 |

## Artifacts
- `data/holdouts/unseen_combo_01/ground_truth.json`
- `data/holdouts/unseen_combo_01/holdout_manifest.json`
