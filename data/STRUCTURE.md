# Data Directory — Ground Truth & Log Inventory
## Last updated: 2026-03-01

This document explains what every folder in `data/` contains, why it exists,
and whether its contents feed into the active training pipeline.

---

## Directory Map

```
data/
├── STRUCTURE.md                      ← this file
│
├── clean_imports/                    ← TRAINING DATA (verified, labeled)
│   ├── forum_batch_local_01/         │  Logs hand-labeled from ArduPilot forum
│   ├── forum_batch_local_02/         │  Each batch has:
│   ├── forum_batch_local_03/         │    benchmark_ready/ground_truth.json
│   ├── forum_batch_local_04/         │    benchmark_ready/dataset/*.bin
│   ├── forum_batch_local_05/         │    manifests/clean_import_manifest.csv
│   ├── forum_batch_local_06/         │
│   ├── forum_batch_unique_01/        │
│   ├── forum_batch_merged_01/        │
│   ├── forum_batch_lockbox_01/       │
│   ├── forum_batch_lockbox_02/       │
│   ├── manual_batch1_extra/          │
│   ├── background_batch_01/          │
│   ├── background_expert_01/         │
│   ├── browser_labeled_batch_01/     │
│   ├── flight_logs_dataset_2026-02-22│
│   ├── forum_smoke/                  │
│   └── newest_mined_logs/            │
│
├── kaggle_backups/                   ← MIRROR (same logs, Kaggle-uploaded copy)
│   └── ardupilot-master-log-pool-v2/ │  45 files, 501 MB
│       ├── ground_truth.json         │  This is what was pushed to Kaggle
│       └── *.bin                     │  DO NOT edit — kept for reproducibility
│
├── holdouts/                         ← TEST SET (never used in training)
│   ├── unseen_combo_01/              │  Reserved for final benchmark only
│   └── unseen_flight_2026-02-22/     │  Treat as production blind test
│
├── to_label/                         ← PENDING REVIEW (separate from training)
│   ├── STRUCTURE.md                  │  ← see below
│   └── provisional_auto_labels_      │  22 high-conf + 10 weak labels
│       2026-03-01.json               │  human_verified=False on all entries
│
├── background_scrapes_batch/         ← RAW CRAWL DATA (not yet labeled)
│   └── *.csv                         │  Forum crawler manifests
│
├── real_training_pool_2026-02-23/    ← LEGACY (superseded by clean_imports)
├── real_training_pool_2026-02-23_    ← LEGACY
│   excl_holdouts/
├── final_training_dataset_2026-02-23/← LEGACY
└── final_training_v2/                ← LEGACY
```

---

## Pipeline Status per Folder

| Folder | Status | Feeds Training? | Count |
|---|---|---|---|
| `clean_imports/*/benchmark_ready/` | ✅ Active | **YES** | 52 logs |
| `kaggle_backups/` | 🔒 Mirror | No (duplicate) | 45 logs |
| `holdouts/` | 🔬 Test-only | **NEVER** | ~10 logs |
| `to_label/` | ⏳ Pending | No (pending review) | 34 logs |
| `background_scrapes_batch/` | 📋 Manifests only | No (no .bin) | — |
| Legacy folders | 🗄 Archive | No | — |

---

## `to_label/` — Provisional Auto-Labels

These are the **35 unlabeled forum logs** from the Kaggle backup that had no
ground truth. They were processed through the hybrid engine on 2026-03-01.

### File: `provisional_auto_labels_2026-03-01.json`

Each entry has:
```json
{
  "filename": "log_0048_oscillation_crash.bin",
  "auto_label": "compass_interference",
  "confidence": 0.85,
  "engine": "rule",
  "evidence": ["mag_field_range=0.41", "mag_field_std=0.25"],
  "rule_top": "compass_interference",
  "rule_conf": 0.85,
  "human_verified": false,    ← MUST be true before using in training
  "status": "auto_labeled_high_confidence",
  "notes": ""                 ← add your observations here
}
```

### How to promote a log to training:

1. Open `provisional_auto_labels_2026-03-01.json`
2. Check `evidence` matches what you'd expect for that flight
3. Set `"human_verified": true` and add a note
4. Run:
   ```bash
   python3 training/promote_verified_labels.py \
     --provisional data/to_label/provisional_auto_labels_2026-03-01.json \
     --output-gt data/clean_imports/human_review_batch_01/benchmark_ready/ground_truth.json
   ```
5. Then rebuild + retrain:
   ```bash
   python3 training/build_dataset.py ...
   python3 training/train_model.py
   ```

---

## Total Data Inventory (as of 2026-03-01)

| Source | Files | Labeled | In Training |
|---|---|---|---|
| Kaggle dataset (3 combined, deduped) | 87 unique | 65 | 52 |
| Wild holdout (forum, SHA-verified) | 1 | ✅ manually confirmed | No |
| To-label (provisional, unverified) | 34 | 22 high-conf auto | No |
| **Total unique .BIN files** | **~122** | | |
| **Total Kaggle disk** | **4.94 GB** | | |
