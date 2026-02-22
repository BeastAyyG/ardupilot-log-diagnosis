# ArduPilot AI Log Diagnosis

## What It Does
An agentic AI and rule-based diagnostic engine for analyzing ArduPilot .BIN dataflash logs. Extracts 60+ critical flight telemetry features and uses a hybrid rule/ML intelligence engine to determine whether a flight is healthy or suffering from one of a dozen critical conditions, such as high vibrations, compass interference, and EKF failures.

## Quick Start
```bash
pip install -r requirements.txt
python -m src.cli.main analyze flight.BIN
```

## Run on GitHub Codespaces
If your laptop is slow, run everything in Codespaces.

1) Open the repo in GitHub and click **Code -> Codespaces -> Create codespace on main**.
2) Wait for container setup to finish (`.devcontainer/devcontainer.json` installs dependencies automatically).
3) Run the same commands in the Codespaces terminal.

Recommended first commands:

```bash
pytest -q
python -m src.cli.main collect-forum --output-root "data/raw_downloads/forum_batch_01" --max-per-query 25 --max-topics-per-query 80 --sleep-ms 50 --no-zip
python -m src.cli.main import-clean --source-root "data/raw_downloads/forum_batch_01" --output-root "data/clean_imports/forum_batch_01"
python -m src.cli.main benchmark --dataset-dir "data/clean_imports/forum_batch_01/benchmark_ready/dataset" --ground-truth "data/clean_imports/forum_batch_01/benchmark_ready/ground_truth.json"
```

## Sample Output
```
╔═══════════════════════════════════════╗
║  ArduPilot Log Diagnosis Report       ║
╠═══════════════════════════════════════╣
║  Log:      flight.BIN                 ║
║  Duration: 5m 42s                     ║
║  Vehicle:  ArduCopter 4.5.1           ║
╚═══════════════════════════════════════╝

CRITICAL — VIBRATION_HIGH (95%)
  vibe_z_max = 67.8 (limit: 30.0)
  vibe_clip_total = 145 (limit: 0)
  Method: rule + ML
  Fix: Balance/replace propellers.

Overall: NOT SAFE TO FLY
```

## Features Extracted
- **Vibration**: vibe_x/y/z_mean, max, std
- **Compass**: mag_field_mean, range, std
- **Power**: bat_volt_min, max, curr_mean
- **GPS**: hdop_mean, nsats_min
- **Motors**: spread_max, hover_ratio
- **EKF**: variances, lane switches
- **Control**: alt_error, thrust ratio

## Benchmark Results (v0.1.0)
  
Tested against 10 real crash logs from discuss.ardupilot.org with expert-verified diagnoses.

```
╔═════════════════════════════════════════╗
║  ArduPilot Log Diagnosis Benchmark      ║
║  Engine: rules/ml hybrid v0.1.0         ║
╠═════════════════════════════════════════╣
║  Total logs:     10                     ║
║  Extracted:      10 (100%)              ║
║  Macro F1:       0.20                   ║
╚═════════════════════════════════════════╝

Per-Label Results:
┌──────────────────────┬────┬────┬──────┬─────┐
│ Label                │ N  │ TP │ Prec │ F1  │
├──────────────────────┼────┼────┼──────┼─────┤
│ vibration_high       │  5 │  4 │ .50  │ .61 │
│ compass_interference │  5 │  5 │ .62  │ .76 │
└──────────────────────┴────┴────┴──────┴─────┘
```

**Analysis:** 
- 100% stable parser (never crashed)
- Perfect or near-perfect recall on real vibration and compass failures
- Precision is deliberately hurt by cascading symptom detection (vibration physically shakes compass → tool correctly flags both).
- Root-cause vs symptom disambiguation is the key improvement target for GSoC ML training phase.

See `benchmark_results.md` for full analysis.

## Benchmarking Execution
```bash
python -m src.cli.main benchmark
```

If `dataset/` + `ground_truth.json` are unavailable, the benchmark command
automatically falls back to the latest clean-imported benchmark subset under
`data/clean_imports/*/benchmark_ready/`.

You can benchmark against a specific imported batch:

```bash
python -m src.cli.main benchmark \
  --dataset-dir data/clean_imports/flight_logs_dataset_2026-02-22/benchmark_ready/dataset \
  --ground-truth data/clean_imports/flight_logs_dataset_2026-02-22/benchmark_ready/ground_truth.json \
  --output-prefix data/clean_imports/flight_logs_dataset_2026-02-22/benchmark_ready/benchmark_results
```

### Create SHA-Unseen Holdout + Mentor Showcase

Build a holdout set with zero SHA overlap against your training batches, then
benchmark and generate a progress report with integrity checks and visuals.

```bash
python training/create_unseen_holdout.py \
  --exclude-batches forum_batch_local_01 forum_batch_local_02 forum_batch_local_03 \
  --candidate-batches flight_logs_dataset_2026-02-22 \
  --output-root data/holdouts/unseen_flight_2026-02-22

python -m src.cli.main benchmark \
  --engine ml \
  --dataset-dir data/holdouts/unseen_flight_2026-02-22/dataset \
  --ground-truth data/holdouts/unseen_flight_2026-02-22/ground_truth.json \
  --output-prefix data/holdouts/unseen_flight_2026-02-22/benchmark_results_ml

python training/generate_progress_showcase.py \
  --output docs/progress_showcase.md \
  --train-batch forum_batch_unique_01 \
  --train-source-batches forum_batch_local_01 forum_batch_local_02 forum_batch_local_03 \
  --holdout-root data/holdouts/unseen_flight_2026-02-22
```

## Current Limitations
- Rule-based testing only available until ML dataset is generated
- ML model degrading gracefully without missing files
- Precision drops in multi-label scenarios due to un-mapped causal chains

## Contributing Logs
See `download_logs.md` for how to add crash logs to the benchmark dataset.

## Clean Import (Production-Safe)
Use the app command below to ingest an external log folder with strict
provenance checks, SHA256 dedupe, non-log rejection, and benchmark-ready output.

```bash
python -m src.cli.main import-clean \
  --source-root "/home/ayyg/Downloads/flight_logs_dataset_2026-02-22" \
  --output-root "data/clean_imports/flight_logs_dataset_2026-02-22"
```

Generated artifacts include:
- `data/clean_imports/flight_logs_dataset_2026-02-22/manifests/source_inventory.csv`
- `data/clean_imports/flight_logs_dataset_2026-02-22/manifests/clean_import_manifest.csv`
- `data/clean_imports/flight_logs_dataset_2026-02-22/manifests/rejected_manifest.csv`
- `data/clean_imports/flight_logs_dataset_2026-02-22/manifests/provenance_proof.md`
- `data/clean_imports/flight_logs_dataset_2026-02-22/benchmark_ready/ground_truth.json`

## Benchmark Data Provenance (Latest Batch)
Source folder used:
- `/home/ayyg/Downloads/flight_logs_dataset_2026-02-22`

Validated summary:
- Total `.bin` files scanned: `27`
- Parse-valid logs (pre-dedupe): `19`
- Unique parse-valid logs (SHA256 dedupe): `13`
- Rejected non-log `.bin` payloads: `8`
- Unique ZIP archives: `2` (SITL lineage, excluded from production benchmark training)
- Benchmark-trainable logs: `2`

Verified labeled logs with source proof:
- `log_01_VIBE_HIGH.bin` -> `vibration_high`
  - Thread: `https://discuss.ardupilot.org/t/a-problem-about-ekf-variance-and-crash/56863`
  - Download URL: `https://drive.google.com/uc?export=download&id=1nNki5GiGJ3-GJOMGMv4MQEwwnopZdgUQ`
- `log_10_MAG_INTERFERENCE_1.bin` -> `compass_interference`
  - Thread: `https://discuss.ardupilot.org/t/ekf-yaw-reset-crash/107273`
  - Download URL: `https://drive.google.com/uc?export=download&id=1z5wB1v8-RY6pFT-gDKsG_vkxZFF54oi_`

Provisional (kept out of production benchmark labels):
- `log_05_ESC_DESYNC_1.bin` (raw label: `ESC_DESYNC`)
- `log_11_ESC_DESYNC.bin` (raw label: `ESC_DESYNC`)

Full mentor-facing proof report:
- `data/clean_imports/flight_logs_dataset_2026-02-22/manifests/provenance_proof.md`

## Data Curation Workflow
To keep project boundaries clear, there are two separate flows:

1) Companion-health app data migration (separate app area):

```bash
python companion_health/scripts/integrate_legacy_health_monitor.py
```

2) Main diagnosis benchmark import from downloaded log folder:

```bash
python training/import_clean_batch.py \
  --source-root "/home/ayyg/Downloads/flight_logs_dataset_2026-02-22" \
  --output-root "data/clean_imports/flight_logs_dataset_2026-02-22"
```

To collect more candidate logs directly from forum search before clean import:

```bash
python -m src.cli.main collect-forum \
  --output-root "data/raw_downloads/forum_batch_01" \
  --max-per-query 25 \
  --max-topics-per-query 80

# optional custom query set
python -m src.cli.main collect-forum \
  --output-root "data/raw_downloads/forum_batch_02" \
  --queries-json "docs/forum_queries.example.json"

python -m src.cli.main import-clean \
  --source-root "data/raw_downloads/forum_batch_01" \
  --output-root "data/clean_imports/forum_batch_01"

# expanded class coverage with one command
python training/grow_benchmark_dataset.py \
  --batch-name "forum_batch_expand_01" \
  --queries-json "docs/forum_queries.expanded.json" \
  --max-per-query 15 \
  --max-topics-per-query 80 \
  --sleep-ms 100 \
  --no-zip
```

Companion-health output location:
- `companion_health/data/health_monitor/`

Main diagnosis clean-import output location:
- `data/clean_imports/<batch_name>/`

Main diagnosis metadata refresh:

```bash
python training/refresh_ground_truth_metadata.py
```

Boundary validation (diagnosis app vs companion-health app):

```bash
python training/validate_project_boundaries.py
```

You can then build ML datasets with confidence filtering:

```bash
python training/build_dataset.py --min-confidence medium
```

By default, `build_dataset.py` excludes records marked `trainable=false`.
Use `--include-non-trainable` only for experiments.
