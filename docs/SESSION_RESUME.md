# Session Resume Guide — 2026-02-26

## Current State Summary

- **Master Pool**: 45 unique deduplicated logs in `data/master_pool/`
- **Label Distribution**: compass_interference(10), vibration_high(9), motor_imbalance(8), ekf_failure(5), power_instability(5), rc_failsafe(5), pid_tuning_issue(2), gps_quality_poor(1)
- **Browser-Labeled Batch**: 28 candidates in `data/to_label/browser_labeled_01/`
- **Background Scrapes**: 41 new .bin files in `data/background_scrapes_batch/downloads/`
- **Kaggle Kernel**: **v9 RUNNING** (with ML engine + Master Pool v2)
- **Kaggle Kernel**: v5 COMPLETED (Rule F1=0.17)

## Benchmark Results (Kaggle v5)

| Engine      | Macro F1 | Exact Match |
|-------------|----------|-------------|
| Rule-Based  | 0.17     | 0.02        |
| Hybrid      | 0.11     | 0.21        |
| ML-only     | 0.00     | 0.00        |

## What Still Needs Doing (Priority Order)

### 1. Human-Review the Browser Labels

File: `data/to_label/browser_labeled_01/ai_label_candidates.json`

- 28 entries with expert quotes from real forum threads
- Note: Some original filenames (e.g., `log_0003_vibration_high.bin`) got re-labeled as `motor_imbalance` because the FORUM COMMUNITY said so
- Review and approve/reject each one

### 2. Rebuild Master Pool After Review

```bash
python3 src/data/merge_batches.py
```

### 3. Train XGBoost Meta-Learner (CRITICAL)

The Kaggle ML benchmark shows 0.00 F1 — no model trained yet.

```bash
# Bundle master pool for Kaggle
python3 training/create_colab_bundle.py --output master_pool_bundle.tar.gz --paths data/master_pool
# Upload to Kaggle and add training code
```

### 4. Get More Labeled Data (Optional)

- ScrapeGraphAI credits exhausted (402 error)
- More credits OR use Browser OS to label remaining 13 no-consensus threads
- Target: 100+ logs for robust XGBoost training

## Key Files Created This Session

- `src/data/auto_labeler.py` — ScrapeGraphAI-based auto-labeler
- `src/data/merge_batches.py` — SHA256 dedup + merge all batches
- `src/data/forum_orchestrator.py` — Simplified orchestrator
- `data/to_label/browser_labeled_01/ai_label_candidates.json` — 28 browser-extracted labels
- `data/master_pool/` — Merged 45-log pool with ground_truth.json

## API Keys (in .env)

- SGAI_API_KEY — ScrapeGraphAI (credits exhausted)
- CRAWLBASE_API_KEY — Crawlbase
- SCRAPER_AI_API_KEY — ScraperAI
- ABSTRACT_API_KEY — AbstractAPI
