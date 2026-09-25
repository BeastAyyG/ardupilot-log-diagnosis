# Progress Timeline (2026-02-23)

## Objective

Grow a real-only ArduPilot diagnosis dataset, preserve provenance integrity, and
benchmark on realistic data while avoiding fabricated labels.

## Chronological Order: What We Did

1. **Productionized unseen-eval workflow and diagnostics tuning**
   - Added holdout/report tooling and classifier/rule/hybrid tuning in earlier commits.
   - Result: stable end-to-end pipeline (collect -> import -> build -> benchmark).

2. **Integrated Batch 1 real logs**
   - Added first manually labeled external logs into `data/to_label/2026-02-23_batch/`.
   - Rebuilt real pool and increased real labeled coverage.

3. **Integrated Batch 2 real logs**
   - Added second set of manually labeled external logs.
   - Rebuilt real pool to 42 SHA-unique logs before later cleanup steps.

4. **Attempted Batch 3 and investigated parser failures**
   - Found one candidate causing hard parser errors (`batch3_brownout_10543.bin`).
   - Found one candidate that was actually HTML (`external_batch3_tmp_healthy_38068.bin`).
   - Lesson: URL/download success does not guarantee valid DataFlash binary payload.

5. **Removed bad sample contamination**
   - Removed invalid temporary label entry from `data/to_label/2026-02-23_batch/ground_truth.json`.
   - Deleted `data/to_label/2026-02-23_batch/external_batch3_tmp_healthy_38068.bin`.
   - Rebuilt final real dataset with only valid samples.

6. **Rebuilt current final dataset**
   - Output: `data/final_training_dataset_2026-02-23/`.
   - Current total: **42** logs.
   - Current label distribution (from `build_summary.json`):
     - `compass_interference`: 8
     - `ekf_failure`: 8
     - `vibration_high`: 8
     - `motor_imbalance`: 7
     - `power_instability`: 5
     - `rc_failsafe`: 4
     - `gps_quality_poor`: 1
     - `pid_tuning_issue`: 1

7. **Prepared cloud migration tooling (to offload laptop)**
   - Added `training/create_colab_bundle.py` for packing data.
   - Added `training/run_all_benchmarks.py` to run `ml + hybrid + rule` in one command.
   - Added quickstarts:
     - `docs/colab_quickstart.md`
     - `docs/kaggle_quickstart.md`
   - Updated `.gitignore` for local env/data/result artifacts.
   - Created bundle: `colab_data_bundle.tar.gz` (~363 MB).
   - SHA256: `81baa8ac01649e3be68e0cd6e5ff6496e0cf493f8fc86cb24f7f9704ec3de0dc`.

## What We Understood

- **Data quality risk is in downloads, not only labels**
  - Some `.bin` URLs return HTML/404 content; strict payload validation is mandatory.

- **Parser stability depends on input hygiene**
  - Invalid files create noisy `bad header` output and extraction failures.
  - Cleaning bad payloads before benchmark is essential.

- **Coverage imbalance is still the main model bottleneck**
  - Stronger classes: `vibration_high`, `compass_interference`, `ekf_failure`.
  - Weak/missing classes still block broad generalization (`healthy`, `brownout`, etc.).

- **Hybrid remains best among current engines**
  - In latest local run before cleanup, hybrid outperformed ML/rule on overall accuracy.
  - Clean rerun is still pending now that invalid samples were removed.

- **Cloud execution is the right next step**
  - Colab/Kaggle can run this CPU workflow reliably and reduce local machine strain.

## Immediate Next Step

Run in Colab or Kaggle using:

```bash
python training/run_all_benchmarks.py \
  --dataset-dir data/final_training_dataset_2026-02-23/dataset \
  --ground-truth data/final_training_dataset_2026-02-23/ground_truth.json \
  --output-dir data/final_training_dataset_2026-02-23
```
