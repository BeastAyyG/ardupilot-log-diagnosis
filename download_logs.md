# Downloading Crash Logs

To collect ArduPilot crash logs, visit `discuss.ardupilot.org`.

## What to Look For
* Look for an expert reply describing the specific issue (e.g. "Chipped propeller causing vibrations").
* Download the `.BIN` attachment.

## Adding to Dataset
* Save the file into `dataset/` directory as `crash_NNN.BIN`.
* Run the interactive CLI command to label it:
  `python -m src.cli.main label crash_NNN.BIN`

## Clean Import from External Folder
If logs are downloaded into a separate folder tree, use the clean-import pipeline:

`python -m src.cli.main import-clean --source-root "/path/to/downloads" --output-root "data/clean_imports/<batch_name>"`

This produces SHA256 manifests, rejects non-log payloads, and writes a
benchmark-ready subset under `benchmark_ready/`.

Companion-health data collection is maintained separately under
`companion_health/` and is not mixed into diagnosis benchmark labels.

## Collect More Data from Forum
Use the built-in forum collector to fetch more candidate logs:

`python -m src.cli.main collect-forum --output-root "data/raw_downloads/forum_batch_01" --max-per-query 25 --max-topics-per-query 80`

Optional custom queries (JSON map label -> query):

`python -m src.cli.main collect-forum --output-root "data/raw_downloads/forum_batch_01" --queries-json "docs/forum_queries.example.json"`

Then normalize and validate with clean import:

`python -m src.cli.main import-clean --source-root "data/raw_downloads/forum_batch_01" --output-root "data/clean_imports/forum_batch_01"`

Review `manifests/provenance_proof.md` and move only verified labels into benchmark training.

## Failure Categories & Forum Search Queries
* `vibration_high`: Search for "high vibration", "clip", "vibe level".
* `compass_interference`: Search for "compass variance", "mag field".
* `motor_imbalance`: Search for "motor loss", "thrust imbalance", "desync".
* `gps_quality_poor`: Search for "gps glitch", "loss of hdop".
