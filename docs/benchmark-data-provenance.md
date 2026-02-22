# Benchmark Data Provenance

This project now uses a reproducible clean-import pipeline for external log batches.

## Project Boundary
- Companion-health app artifacts are maintained under `companion_health/`.
- Main diagnosis benchmark data is maintained under `data/clean_imports/`.
- Companion-health data is excluded from benchmark labels unless explicitly reviewed and promoted.

## Batch
- Source folder: `/home/ayyg/Downloads/flight_logs_dataset_2026-02-22`
- Import output: `data/clean_imports/flight_logs_dataset_2026-02-22`

## Quality Gates
- Binary signature gate rejects image/html/pdf payloads masquerading as `.bin`
- DataFlash parse probe gate confirms logs are parseable
- SHA256 dedupe gate removes duplicate files across download folders
- Provenance gate requires source manifest evidence for trainable labels
- Taxonomy gate excludes provisional labels from production benchmark labels
- Synthetic gate excludes SITL ZIP lineage from production benchmark labels

## Latest Numbers
- Total `.bin` scanned: `27`
- Parse-valid `.bin` (pre-dedupe): `19`
- Unique parse-valid logs (dedupe): `13`
- Rejected non-log `.bin`: `8`
- Unique ZIP archives: `2`
- Benchmark-trainable logs: `2`

## Source Links Used for Trainable Labels
- `https://discuss.ardupilot.org/t/a-problem-about-ekf-variance-and-crash/56863`
- `https://discuss.ardupilot.org/t/ekf-yaw-reset-crash/107273`

## Artifacts
- `data/clean_imports/flight_logs_dataset_2026-02-22/manifests/source_inventory.csv`
- `data/clean_imports/flight_logs_dataset_2026-02-22/manifests/clean_import_manifest.csv`
- `data/clean_imports/flight_logs_dataset_2026-02-22/manifests/rejected_manifest.csv`
- `data/clean_imports/flight_logs_dataset_2026-02-22/manifests/provenance_proof.md`
- `data/clean_imports/flight_logs_dataset_2026-02-22/benchmark_ready/ground_truth.json`
