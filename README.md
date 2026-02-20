# ArduPilot Log Diagnosis Prototype 

![ArduPilot](https://img.shields.io/badge/Platform-ArduPilot-blue.svg)
![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

A lightweight, object-oriented Python prototype developed for the **GSoC 2025: Project 5 (AI-Assisted Log Diagnosis)** application. 

This repository demonstrates a foundational pipeline for parsing ArduPilot DataFlash `.BIN` logs, extracting statistical telemetry features, and applying heuristic rules to diagnose common hardware and configuration issues.

## 🚀 Key Capabilities

- **Robust Data Ingestion:** Uses `pymavlink` to parse raw telemetry streams including `VIBE`, `MAG`, `BAT`, `GPS`, and `RCOU`.
- **Statistical Feature Extraction:** Aggregates time-series data into actionable features (e.g., max vibrations, voltage sags, magnetic field variance).
- **Explainable Inference Engine:** Runs a deterministic ruleset against the extracted features to identify:
  - 🚁 **Vibration Issues** (Imbalanced props, loose mounts)
  - 🧲 **Compass Interference** (Wiring proximity, calibration issues)
  - 🔋 **Power Issues** (Voltage sags, battery health)
  - 🛰️ **GPS Degradation** (High HDOP, low satellite count)
  - ⚖️ **Motor Imbalance** (Twisted mounts, CG issues)
- **Confidence Scoring:** Outputs a formatted diagnostic report weighted by the severity and number of triggered heuristics.

## 🛠️ System Architecture

The codebase is structured using an Object-Oriented approach for modularity and future expansion into a Machine Learning pipeline:

1. `log_parser.py`: Scans the `.BIN` file and summarizes available message frequencies.
2. `feature_extractor.py`: Aggregates the raw MAVLink data into a flattened JSON structure of mathematical features.
3. `diagnosis_engine.py`: Correlates the extracted features against known failure thresholds and outputs human-readable recommendations.

## ⚙️ Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Extract Features
To parse a `.BIN` file and save its statistical features to a JSON file:
```bash
python3 feature_extractor.py path/to/your_flight.BIN
```

### 3. Run Diagnostic Engine
To run the full pipeline and print a formatted health report:
```bash
python3 diagnosis_engine.py path/to/your_flight.BIN
```

## 📊 Example Output
```text
============================================================
                 LOG DIAGNOSIS REPORT
============================================================

[100%] VIBRATION_ISSUE
  -> vibe_x_max = 45.20 (threshold: > 30.0)
  -> vibe_y_max = 52.10 (threshold: > 30.0)
  -> clip_total = 12.00 (threshold: > 0.0)
  Fix: Balance propellers, tighten motor mounts, or improve flight controller damping.

[50%] POWER_ISSUE
  -> volt_min = 9.80 (threshold: < 10.5)
  Fix: Check battery health, internal resistance, and verify power module calibration.

============================================================
```

## 👨‍💻 Author
**BeastAyyG** - GSoC 2025 Applicant
*Built to understand the ArduPilot ecosystem and establish a baseline for Project 5.*
