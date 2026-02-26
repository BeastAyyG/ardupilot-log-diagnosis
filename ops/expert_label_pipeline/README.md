# Expert Label Pipeline

This folder stores the repeatable workflow for mining logs that already have a
human diagnosis from ArduPilot Developer/staff posts.

## Why this exists

- Avoid spending time on unlabeled logs.
- Avoid duplicate work on logs/topics already in existing datasets.
- Keep outputs in clean-import compatible format (`crawler_manifest_v2.csv` and
  `block1_ardupilot_discuss.csv`).

## Pipeline Modes

1. **Enrich-only mode**
   - Uses an existing crawler manifest.
   - Fetches topic JSON and extracts Developer/staff diagnosis text.
   - Writes labeled manifest + block1 file for the same batch.

2. **Mining mode**
   - Runs searches, filters to topics with Developer/staff diagnosis, then
     downloads attachments.
   - Skips topics already present in existing labeled ground-truth files by
     default.
   - Keeps incremental state in `expert_miner_state.json`.

## Quick Start

### A) Enrich an existing batch (fastest)

```bash
python3 -m src.cli.main mine-expert-labels \
  --enrich-only \
  --source-root data/background_scrapes_batch
```

Expected outputs in `data/background_scrapes_batch/`:

- `crawler_manifest_v2.csv`
- `block1_ardupilot_discuss.csv`
- `expert_label_summary.json`

Then run clean import from the batch root (not `downloads/`):

```bash
python3 -m src.cli.main import-clean \
  --source-root data/background_scrapes_batch \
  --output-root data/clean_imports/background_expert_01
```

### B) Run new expert-only mining

```bash
python3 -m src.cli.main mine-expert-labels \
  --output-root data/raw_downloads/expert_batch_$(date +%F) \
  --queries-json ops/expert_label_pipeline/queries/crash_analysis_high_recall.json \
  --after-date 2026-01-01 \
  --max-topics-per-query 150 \
  --max-downloads 300 \
  --sleep-ms 350
```

Then clean import from this new batch root:

```bash
python3 -m src.cli.main import-clean \
  --source-root data/raw_downloads/expert_batch_$(date +%F) \
  --output-root data/clean_imports/expert_batch_$(date +%F)
```

## Artifacts and meaning

- `crawler_manifest_v2.csv`: provenance rows with `normalized_label` extracted
  from Developer/staff diagnosis text.
- `block1_ardupilot_discuss.csv`: expert quote map consumed by clean import.
- `crawler_summary_v2.json`: mining metrics.
- `expert_miner_state.json`: incremental memory (seen topics/URLs).

## Guardrails

- Label source is human text from Developer/staff posts; no synthetic labels.
- If diagnosis text is uncertain/weak, label is left blank.
- Existing labeled topic URLs are skipped by default to reduce duplicates.
