# `data/to_label/` — Provisional Labels Awaiting Human Review

> ⚠️ **Nothing in this folder feeds the active training pipeline.**  
> These logs are kept here to show work-in-progress and what the engine found.

---

## What is this?

These are **35 raw forum .BIN files** collected from the ArduPilot community that had
no expert ground-truth label. They were discovered during the Kaggle data audit on
2026-03-01 while reviewing the `ardupilot-complete-raw-data-backup-2026` dataset.

They represent **new failure scenarios** the model has never been trained on:
- `oscillation_crash` (8 files)
- `flyaway` (10 files)  
- `battery_failsafe` (3 files)
- `radio_failsafe` (3 files)
- `hardware_failure` (1 file)
- `uncontrolled_descent` (1 file)
- Generic forum logs (9 files)

---

## Files

| File | Date Generated | Method | Count |
|---|---|---|---|
| `provisional_auto_labels_2026-03-01.json` | 2026-03-01 | Hybrid engine (rule + ML) | 34 logs |

---

## Auto-label Results Summary

| Status | Count | Meaning |
|---|---|---|
| `auto_labeled_high_confidence` | 22 | conf ≥ 0.65 — engine is confident |
| `auto_labeled_low_confidence` | 10 | conf < 0.65 — human must verify |
| `no_diagnosis` | 1 | no features triggered — tagged `crash_unknown` |
| `parse_failed` | 1 | `flash.bin` — not a flight log |

**High-confidence breakdown:**
```
compass_interference   10
motor_imbalance         8
gps_quality_poor        2
rc_failsafe             1
ekf_failure             1
```

### Key Finding

The filenames said `oscillation_crash` and `flyaway` — but the actual log features
showed `compass_interference` and `motor_imbalance` as the physical root cause.
This demonstrates that **event name ≠ root cause**, and is exactly why expert
label review matters before training.

---

## How to Review & Promote

```bash
# 1. Open the provisional file and review each entry's 'evidence' field
#    Set "human_verified": true for ones you agree with

# 2. Run the promotion script (creates a new clean_imports batch)
python3 training/promote_verified_labels.py \
  --provisional data/to_label/provisional_auto_labels_2026-03-01.json \
  --output-dir  data/clean_imports/human_review_batch_01/

# 3. Rebuild training dataset
python3 training/build_dataset.py \
  --ground-truth /tmp/unified_ground_truth.json \
  --dataset-dir  data/kaggle_backups/ardupilot-master-log-pool-v2

# 4. Retrain model
python3 training/train_model.py
```

---

## Separation Policy

| Decision | Reason |
|---|---|
| These files are **not** in `clean_imports/` | Auto-labels are not verified |
| These files are **not** in `holdouts/` | They're not a test set |
| `human_verified` flag is **always false** initially | Prevents accidental training use |
| Kept near `clean_imports/` in directory | Easy to navigate and compare |
| Git-tracked (JSON only, not .bin) | Audit trail of what the engine found |

---

*Last updated: 2026-03-01 by Agastya Pandey*
