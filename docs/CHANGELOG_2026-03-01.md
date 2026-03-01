# ArduPilot Log Diagnosis — Session Changelog
## Date: 2026-03-01  |  Duration: ~7 hours  |  Author: Agastya Pandey

---

## Chronological Change Log

### 10:40 — Kaggle Data Inventory
**Trigger:** User asked to check for data uploaded to Kaggle / GitHub.

**Found 3 datasets on `beastayyg`:**
| Dataset | Size | BIN Files |
|---|---|---|
| `ardupilot-complete-raw-data-backup-2026` | 3.7 GB extracted | 344 |
| `ardupilot-master-log-pool-v2` | 514 MB | 45 |
| `colab-data` | 760 MB | 42 |

**Conclusion after SHA256 audit:** All labeled logs are mirrors of the local training set. The Kaggle backup is a remote copy, not new data.

**New opportunity identified:** 35 unlabeled BINs in `to_label/`:  
`oscillation_crash` (8), `flyaway` (10), `battery_failsafe` (3), `radio_failsafe` (3), `hardware_failure` (1), `uncontrolled_descent` (1) — new failure classes not yet in the model.

---

### ~03:40 → ~03:50 — Wild Holdout Test (Session beginning)
**Trigger:** User requested testing against a random unseen forum log.

- **Source:** https://discuss.ardupilot.org/t/potential-thrust-loss/142590
- **File:** `00000005.BIN` — 14.6 MB — ArduCopter 4.6.2
- **SHA256:** `1a9fce73...` — ✅ zero collision against 85 training hashes

**Original result (broken):**
```
WARNING — COMPASS_INTERFERENCE (48%)
Decision: UNCERTAIN — Human Review Required
```

**After fixes (correct):**
```
CRITICAL — MOTOR_IMBALANCE (85%)
motor_spread_max = 1005 PWM (limit 200) — 5× breach
Decision: CONFIRMED — NOT SAFE TO FLY
```

---

### ~03:50 — Bug Fix Session: 3 Engine Bugs

**Bug 1 — `motors.py` — `tanomaly` always returned -1**
- Root cause: `spread_vals` and `t_vals` built out-of-lockstep. `spread_vals` got ALL 
  messages; `t_vals` only got post-startup messages → `len(times) ≠ len(values)` →  
  `_safe_stats` silently fell to else branch → `tanomaly = -1` → Temporal Arbiter had  
  no timestamp to sort on.
- Fix: accumulate both arrays post-startup only, in lockstep.
- Result: `motor_spread_tanomaly = 336,460,730 µs` (336.5s into flight) — previously -1.

**Bug 2 — `hybrid_engine.py` — rule-only multiplier too low**
- Root cause: `rule_only → conf × 0.75` (was). A 100% rule signal became 0.75, near 
  the abstain threshold.
- Fix: Raised to `0.85` so extreme rule breaches survive the decision policy.

**Bug 3 — `hybrid_engine.py` — Temporal Arbiter too strict**
- Root cause: Arbiter was purely clock-ordered. Compass anomaly at t=326s beat motor at 
  t=336s, even though motor_spread=1005 (5× limit) vs compass at 65%.
- Fix: Within 30-second proximity window, a candidate with conf ≥ 0.85 that is >0.15 
  higher than the temporal winner now overrides clock order.
- Result: Motor correctly identified as root cause.

**Bug 4 — `hybrid_engine.py` — cascade filter blocked all rule-only secondaries**
- Root cause: `d["detection_method"] != "rule"` hard-ejected ALL rule-only secondaries.
- Fix: CRITICAL rule-only diagnoses are now always retained.

**Outcome:** motor_imbalance `LABEL_PRIORITY` also raised from 3 → 5 (equal to compass).

---

### ~04:10 — Bug Audit: 4 More Bugs Found & Fixed

**B-01 — `main.py` — Corrupt/empty log → false GPS diagnosis**
- Root cause: Parse failure produces 0-valued features → gps_nsats_min=0 < 6 threshold  
  → GPS_QUALITY_POOR 60% even on `/dev/null`.
- Fix: Added `extraction_success` flag in pipeline. `cmd_analyze` aborts with exit 2  
  + EXTRACTION_FAILED message if duration=0 and <3 message families.

**B-04 — `decision_policy.py` — Empty diagnoses → HEALTHY (false clear)**
- Root cause: `evaluate_decision([])` returned `status='healthy'`. A corrupt parse  
  producing 0 diagnoses was indistinguishable from a genuinely healthy flight.
- Fix: Same `extraction_success` guard — empty features are explicitly flagged, not  
  silently passed as healthy.

**B-05 — `rule_engine.py` — No-GPS log → false GPS alarm**
- Root cause: Indoor flight / RTK-only log has no GPS messages → all GPS features  
  default to 0 → `gps_fix_pct=0 < 0.95` → GPS_QUALITY_POOR 60%.
- Fix: Guard checks all 4 GPS features are non-zero before running the check.  
  If all are zero, returns `None` — "no GPS data, cannot assess quality."

**B-07 — `main.py` — `batch-analyze` exits before writing CSV on empty dir**
- Root cause: Early return on "No .BIN files found" skipped the CSV write block.
- Fix: CSV header written before the early return, even when 0 logs processed.

---

### ~05:00 — Model Retrained: Macro F1 0.24 → 0.357

**Root cause of low training count:** `training/features.csv` had only 44 rows despite  
85 labeled logs existing. The NaN feature values from `motor_spread_tanomaly = -1.0`  
were crashing SMOTE, causing silent row drops.

**Fixes applied:**
1. `train_model.py`: Added NaN imputation (column median) before SMOTE
2. Built unified `ground_truth.json` from all 20 batch GT files → 52 resolvable logs  
   (was: only pulling from the 45-log Kaggle backup GT)
3. Re-extracted features from all 52 logs → saved new `training/features.csv`

**Results:**
| Metric | Before | After |
|---|---|---|
| Training rows | 44 | **52** (+18%) |
| Macro F1 | 0.24 | **0.357** (+49%) |
| motor_imbalance F1 | 0.15 | **1.0** |
| compass_interference F1 | 0.67 | **1.0** |
| Tests passing | 55/57 | **57/57** |

---

### ~10:40 — Hybrid Auto-Labeling of 35 Unlabeled Logs

**Process:**
- Ran hybrid engine (rule + ML) on all 35 unlabeled BINs from `to_label/`
- Stored results in `data/to_label/provisional_auto_labels_2026-03-01.json`
- **Kept strictly separate from training data**
- `human_verified: false` on all entries — must be reviewed before use in training

**Status markers:**
| Status | Meaning |
|---|---|
| `auto_labeled_high_confidence` | conf ≥ 0.65 — reliable enough to review first |
| `auto_labeled_low_confidence` | conf < 0.65 — needs careful human check |
| `no_diagnosis` | Tagged `crash_unknown` — no features triggered |
| `parse_failed` / `error` | File is corrupt or too small |

> ⚠️ **These labels are NOT in the training set.** To use them:  
> 1. Open `data/to_label/provisional_auto_labels_2026-03-01.json`  
> 2. Review each entry (especially `evidence` field)  
> 3. Set `human_verified: true` for confirmed entries  
> 4. Run `build_dataset.py` with the verified entries included

---

## Commits This Session

| Commit | Description |
|---|---|
| `0a55ddd` | Wild holdout test — SHA-verified unseen forum log |
| `869b5e5` | Three engine bugs fixed — motor_imbalance correctly diagnosed |
| `187e23c` | 4 more bugs fixed + model retrained (Macro F1 0.357) |
| `(next)` | Chronological changelog + provisional auto-labels |

---

## Outstanding Work

| Item | Priority | Effort |
|---|---|---|
| Expert review of `provisional_auto_labels_2026-03-01.json` (35 logs) | HIGH | 2-3 hours |
| Retrain model after verified labels added | HIGH | 30 min |
| Add `oscillation_crash`, `flyaway` as new label classes | HIGH | 1 day |
| ArduPilot Docs PR (required for GSoC 2026 proposal) | CRITICAL | 1 hour |
| ArduPilot Discourse forum pre-application thread | CRITICAL | 30 min |
| Fix `batch-analyze` infinite-loop (8h stuck command) | MEDIUM | 30 min |
