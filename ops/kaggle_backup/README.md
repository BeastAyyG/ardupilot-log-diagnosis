# Kaggle Backup Sync

This folder contains the runbook and scripts to recover the saved Kaggle master
dataset backup.

## Source Dataset

- Kaggle owner: `beastayyg`
- Dataset: `ardupilot-master-log-pool-v2`
- Expected payload:
  - `45` `.bin` logs
  - `ground_truth.json` with `45` entries

## One-command sync

```bash
python3 ops/kaggle_backup/sync_master_pool_from_kaggle.py \
  --dataset-ref beastayyg/ardupilot-master-log-pool-v2 \
  --output-dir data/kaggle_backups/ardupilot-master-log-pool-v2 \
  --sync-master-pool
```

## What the script does

1. Lists files from Kaggle for the dataset ref.
2. Downloads and unzips the dataset into `--output-dir`.
3. Validates expected counts (`45` logs + `ground_truth.json`).
4. Optionally syncs those files into `data/master_pool/`.
5. Writes a machine-readable sync report:
   - `data/kaggle_backups/ardupilot-master-log-pool-v2/kaggle_sync_report.json`

## Manual commands

List files:

```bash
kaggle datasets files beastayyg/ardupilot-master-log-pool-v2 --page-size 200 -v
```

Download only:

```bash
kaggle datasets download \
  -d beastayyg/ardupilot-master-log-pool-v2 \
  -p data/kaggle_backups/ardupilot-master-log-pool-v2 \
  --unzip
```
