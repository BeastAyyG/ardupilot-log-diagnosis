# ArduPilot AI Log Diagnosis

This project is a prototype for an ArduPilot AI Log Diagnosis tool. It aims to automate the analysis of ArduPilot telemetry logs to identify potential issues, anomalies, and provide actionable insights.

## Features

*   **Log Parser:** Extracts relevant data from ArduPilot logs (e.g., `.bin` files) using `pymavlink`.
*   **Feature Pipeline:** Processes raw log data into meaningful features for analysis.
*   **Diagnosis Engine:** A rule-based and potentially ML-driven engine to diagnose issues based on extracted features.
*   **JSON Reporting:** Generates structured reports of the diagnosis results.
*   **CLI:** A basic command-line interface for interacting with the tool.

## Project Structure

*   `src/`: Contains the main source code modules.
    *   `parser/`: Log parsing logic.
    *   `features/`: Feature extraction and processing.
    *   `diagnosis/`: Diagnosis rules and models.
    *   `retrieval/`: Data retrieval mechanisms.
    *   `reporting/`: Report generation.
    *   `integration/`: Integration with other systems.
*   `models/`: Directory for storing trained machine learning models.
*   `training/`: Scripts and data for training models.
*   `tests/`: Unit and integration tests.
*   `docs/`: Project documentation.

## Setup

1.  Ensure you have Python 3.8+ installed.
2.  Install the required dependencies:
    ```bash
    pip install -r requirements.txt
    ```
    Or install the package locally:
    ```bash
    pip install -e .
    ```

## Run Diagnosis

```bash
python3 ardupilot_diagnose.py /path/to/flight.BIN \
  --output-json reports/diagnosis.json \
  --legacy-payload reports/legacy_payload.json
```

Optional flags:
- `--model models/model.pkl`: custom model artifact path.
- `--thresholds src/diagnosis/config/thresholds.yaml`: custom rule profile config.
- `--vehicle-profile copter|plane|rover|sub|default`: force profile.
- `--print-features`: print full feature vector.

## Build Dataset

Synthetic only:
```bash
python3 src/training/build_dataset.py --samples 2000 --output data/synthetic_logs.csv
```

Hybrid real + synthetic:
```bash
python3 src/training/build_dataset.py \
  --manifest data/labeled_logs_manifest.csv \
  --samples 1000 \
  --output data/hybrid_dataset.csv
```

Manifest CSV columns:
- `log_path` (required)
- `target` (required)
- `session_id` (optional, used for group-aware train/test splitting)

## Train Model

```bash
python3 src/training/train_model.py \
  --data data/hybrid_dataset.csv \
  --output models/model.pkl \
  --metrics-output models/model.metrics.json
```

Artifact now stores:
- model weights
- exact feature list/schema version
- label map
- training metadata and split strategy

## Tests

Run all tests:
```bash
pytest -q ardupilot-log-diagnosis/tests
```
