#!/usr/bin/env bash
set -euo pipefail

DATE_TAG="$(date +%F)"
BATCH_ROOT="data/raw_downloads/expert_batch_${DATE_TAG}"
CLEAN_ROOT="data/clean_imports/expert_batch_${DATE_TAG}"

python3 -m src.cli.main mine-expert-labels \
  --output-root "${BATCH_ROOT}" \
  --queries-json ops/expert_label_pipeline/queries/crash_analysis_high_recall.json \
  --max-topics-per-query 150 \
  --max-downloads 300 \
  --sleep-ms 350

python3 -m src.cli.main import-clean \
  --source-root "${BATCH_ROOT}" \
  --output-root "${CLEAN_ROOT}"

echo "Daily expert pipeline completed"
echo "batch=${BATCH_ROOT}"
echo "clean=${CLEAN_ROOT}"
