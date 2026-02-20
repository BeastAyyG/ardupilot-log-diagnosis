# Downloading Crash Logs

To collect ArduPilot crash logs, visit `discuss.ardupilot.org`.

## What to Look For
* Look for an expert reply describing the specific issue (e.g. "Chipped propeller causing vibrations").
* Download the `.BIN` attachment.

## Adding to Dataset
* Save the file into `dataset/` directory as `crash_NNN.BIN`.
* Run the interactive CLI command to label it:
  `python -m src.cli.main label crash_NNN.BIN`

## Failure Categories & Forum Search Queries
* `vibration_high`: Search for "high vibration", "clip", "vibe level".
* `compass_interference`: Search for "compass variance", "mag field".
* `motor_imbalance`: Search for "motor loss", "thrust imbalance", "desync".
* `gps_quality_poor`: Search for "gps glitch", "loss of hdop".
