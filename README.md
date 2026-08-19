<div align="center">

# 🚁 ArduPilot AI Log Diagnosis

[![CI](https://github.com/BeastAyyG/ardupilot-log-diagnosis/actions/workflows/ci.yml/badge.svg)](https://github.com/BeastAyyG/ardupilot-log-diagnosis/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests: 338 Passing](https://img.shields.io/badge/tests-338%20passing-brightgreen)](tests/)
[![Honest Candidate Macro F1: 0.500](https://img.shields.io/badge/honest%20candidate%20Macro%20F1-0.500-orange)](#-production-benchmark-results)
[![GSoC 2026](https://img.shields.io/badge/GSoC%202026-Ready-purple)](docs/GSOC_2026_Application.md)

**An end-to-end, read-only diagnostic pipeline for ArduPilot DataFlash `.BIN/.LOG` logs, with optional PX4 ULog, MAVLink TLog, and Betaflight Blackbox adapters.**

Drop a flight log → get evidence-backed diagnoses, quality/coverage status, causal timelines, exports, and actionable review recommendations. The engine abstains when the log cannot support a reliable claim.

*Built for the Google Summer of Code 2026 program.*

<br/>

<img src="docs/assets/dashboard_landing.png" alt="ArduPilot AI Log Diagnosis Dashboard" width="800"/>

<sub>Interactive dashboard with drag-and-drop multi-format flight-log analysis</sub>

</div>

> [!WARNING]  
> **IMPORTANT CONTACT UPDATE:** My previous Discord account (**`Mommychorr07`**) was hacked and I no longer control it. Please ignore any messages from it. If you need to reach me regarding this project, please message my new Discord account: **`MommyChorrr`** or reach out via email.


---

## Table of Contents

- [What This Does](#-what-this-does)
- [Quick Start](#-quick-start)
- [Interactive Dashboard](#-interactive-dashboard)
- [How It Works (Architecture)](#-how-it-works--architecture)
- [CITA — Crash-Immune Temporal Arbitration](#-crash-immune-temporal-arbitration-cita)
- [111 Features Extracted](#-111-features-extracted)
- [Production Benchmark Results](#-production-benchmark-results)
- [All Usage Modes](#-all-usage-modes)
- [Data Pipeline & Training](#-data-pipeline--training)
- [Cloud Execution](#-cloud-execution)
- [Recent Audit & Fixes (March 2026)](#-recent-audit--fixes-march-2026)
- [Project Structure](#-project-structure)
- [GSoC 2026 Roadmap](#-gsoc-2026-the-12-week-roadmap)
- [Key Documents](#-key-documents)
- [Contributing](#-contributing)
- [License](#-license)

---

## 🎯 What This Does

ArduPilot flight logs contain thousands of telemetry messages across dozens of subsystems. When something goes wrong, diagnosing **why** a drone crashed requires expert knowledge of ArduPilot internals, and hours of manual parameter analysis.

This tool automates that entire process:

| Problem | Solution |
|---|---|
| **Manual crash analysis is slow** | Fast offline parsing with structured evidence and exports |
| **Post-crash noise can look causal** | **CITA temporal arbitration** preserves onset order and abstains when evidence is weak |
| **Logs are incomplete or sparse** | Per-capability quality gates identify supported, degraded, and unsupported analyses |
| **Hard to visualize what happened** | **3D flight replay** with causality markers at exact GPS coordinates |
| **Labels can be unreliable** | Provenance, SHA256 deduplication, grouped holdouts, and expert-label gates |

### What You Get

```
╔═══════════════════════════════════════╗
║  ArduPilot Log Diagnosis Report       ║
╠═══════════════════════════════════════╣
║  Log:      flight.BIN                 ║
║  Duration: 5m 42s                     ║
║  Vehicle:  ArduCopter 4.5.1           ║
╚═══════════════════════════════════════╝

=== PRE-FLIGHT PARAMETER VALIDATION ===
⚠️ WARNING: ATC_RAT_RLL_P is at default (0.135)
   Log shows heavy oscillation (vibe_z_max = 67.8).
   Bad tuning likely preceded mechanical failure.

=== HYPOTHESIS SCAFFOLDING ===
CRITICAL — THRUST_LOSS (92%)
  rcou_pegged_duration = 4.2s  |  alt_drop = 1.5m
  Onset: T+140s
  Method: rule+ml

WARNING — EKF_FAILURE (72%)
  Onset: T+147s (7 seconds after Thrust Loss)

=== CAUSAL ARBITER DECISION ===
Root Cause: THRUST_LOSS
Reason: thrust_loss preceded ekf_failure by 7.0s.

FILTERED (Post-Crash Noise):
- COMPASS_INTERFERENCE: Onset at T+195s (filtered as post-crash impact noise)
```

---

## ⚡ Quick Start

### Prerequisites

- **Python 3.10+**
- **pip** (comes with Python)

### One-Line Install

```bash
# Clone the repository
git clone https://github.com/BeastAyyG/ardupilot-log-diagnosis.git
cd ardupilot-log-diagnosis

# Install (creates venv, installs all dependencies)
pip install -e ".[dev]"
```

### Analyze Your First Log

```bash
# Analyze an ArduPilot .BIN/.LOG file (or a supported generic ULog/TLog)
python -m src.cli.main analyze path/to/your/flight.BIN

# Include read-only CITA-Nexus causal evidence in the report
python -m src.cli.main analyze flight.BIN --nexus

# Try the built-in sample log (no BIN file needed)
python -m src.cli.main demo

# Generate a shareable HTML report
python -m src.cli.main analyze flight.BIN --format html -o report.html
```

### On Linux/macOS with bootstrap.sh

```bash
./bootstrap.sh setup     # Create venv + install everything
./bootstrap.sh demo      # Try an instant demo
./bootstrap.sh analyze flight.BIN   # Analyze a real log
./bootstrap.sh test      # Run the full regression suite
```

### On Windows (PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -m src.cli.main analyze flight.BIN
```

---

## 🌟 Interactive Dashboard

Launch the premium web dashboard for visual analysis with 3D flight replay, subsystem radar, and crash causality timelines:

```bash
python -m src.cli.main ui
# → Open http://localhost:8000 in your browser
```

**Dashboard Features:**

| Feature | Description |
|---|---|
| 🎯 **Drag & Drop Analysis** | Upload `.BIN`, `.LOG`, `.ULG/.ULOG`, `.TLOG`, `.BBL`, or `.BFL` logs |
| 🗺️ **3D Flight Trajectory** | Full X/Y/Z path reconstruction with Plotly.js |
| 📍 **Causality Markers** | Interactive markers at exact GPS coordinates where anomalies occurred |
| 📊 **Subsystem Radar** | Dynamic "Blame Ranking" chart showing which subsystem failed |
| ⏱️ **Crash Timeline** | Swimlane visualization with color-coded severity events |
| 📈 **Vibration Plots** | Real-time VibeX/Y/Z telemetry charts |
| 🤖 **AI Integrity Report** | Side-by-side comparison: Legacy Rule Engine vs Hybrid AI decision |

---

## 🏗️ How It Works — Architecture

The diagnosis pipeline converts a raw `.BIN` log into an actionable root-cause verdict in 5 stages:

```
 ┌──────────┐    ┌───────────────┐    ┌──────────────┐    ┌──────────────────┐    ┌───────────┐
 │  .BIN    │───▶│  LogParser    │───▶│  Feature     │───▶│  Hybrid Engine   │───▶│  Report   │
 │  File    │    │  Parser/adapters│    │  Pipeline    │    │  Rule + ML + safety│    │  Output   │
 └──────────┘    │               │    │  111 features│    │  + CITA Arbiter  │    └───────────┘
                 │  24,837 msgs  │    │              │    │  + Anomaly Det.  │
                 │  809 params   │    │  per log     │    │                  │
                 └───────────────┘    └──────────────┘    └──────────────────┘
```

### How Each Layer Works

| Stage | Module | What It Does |
|---|---|---|
| **1. Parsing** | `src/parser/bin_parser.py` | Uses `pymavlink` to decode binary DataFlash messages (VIBE, MAG, GPS, EKF, RCOU, BAT, IMU, etc.) |
| **2. Feature Extraction** | `src/features/pipeline.py` | Extracts **111 finite features** across telemetry, control, power, system, and temporal subsystems |
| **3a. Rule Engine** | `src/diagnosis/rule_engine.py` | 13 deterministic threshold checks based on ArduPilot domain knowledge |
| **3b. ML Classifier** | `src/diagnosis/ml_classifier.py` | Versioned artifact with schema/hash checks; candidate promotion is blocked until release gates pass |
| **3c. Anomaly Detector** | `src/diagnosis/anomaly_detector.py` | IsolationForest trained on healthy flights — catches unknown failure modes |
| **4. Hybrid Fusion** | `src/diagnosis/hybrid_engine.py` | Merges rule + ML signals using confidence weighting and temporal arbitration |
| **5. Output** | `src/cli/` or `src/web/` | CLI text report, JSON, HTML, or interactive dashboard |

### Vehicle-Aware Routing

The engine auto-detects vehicle type from boot text and `FRAME_CLASS`:

| Vehicle | Checks Applied |
|---|---|
| **Copter / QuadPlane** | All 13 checks: vibration, compass, GPS, EKF, motors, power, thrust, PID, RC, events, system |
| **Rover** | Compass, power, GPS, EKF, system, RC, events (no motor/vibration/thrust) |
| **Sub** | Compass, power, EKF, system, RC, events (no GPS/motor checks) |

---

## 🛡️ Crash-Immune Temporal Arbitration (CITA)

**The key innovation.** CITA solves the #1 problem in automated crash analysis: **post-crash noise**.

### The Problem

When a drone hits the ground, the impact generates massive compass interference, EKF spikes, and GPS jumps. A naive ML model trained on raw log data will see these post-impact signals and misdiagnose them as the *cause* of the crash. This is the **"compass hallucination" problem** — well-known in the ArduPilot community.

### The Solution

Every feature extractor computes a `t_anomaly` timestamp: the **exact microsecond** a parameter first breached its anomaly threshold. The Causal Arbiter then reconstructs the failure chain by sorting these onset times:

| Step | What Happens |
|---|---|
| 1. Feature Extraction | Each extractor (VIBE, MAG, GPS, EKF, BAT, RCOU) computes `t_anomaly` — first threshold breach time |
| 2. Onset Sorting | All candidate diagnoses are sorted by `t_anomaly` (earliest first) |
| 3. Tie-Breaking | Within 5s: highest confidence wins. Within 30s: extreme-confidence signals can override |
| 4. Post-Crash Filtering | Signals that appear only after the earliest critical onset are suppressed |

**Result:** A vibration spike at T-45s that cascades into EKF divergence at T-20s is correctly labeled as `vibration_high`, not `ekf_failure` — regardless of what the crash-impact data looks like.

> **Key difference from fixed-window approaches:** CITA doesn't just crop the log to 30 seconds. It computes per-subsystem onset timestamps and builds a causal chain. This means it correctly handles cases where the root cause is a slow degradation (e.g., power brownout over 2 minutes) that a fixed window would miss entirely.

See [`docs/root_cause_policy.md`](docs/root_cause_policy.md) for the authoritative spec.

---

## 📦 111 Features Extracted

Every supported flight log is normalized into a flat vector of **111 finite runtime features**. Features are extracted when their required telemetry exists and are marked degraded or unsupported when it does not.

| Category | Count | Key Features |
|---|---|---|
| 📳 **Vibration** | runtime family | VIBE/IMU statistics, clipping, and temporal onset |
| 🧭 **Navigation** | runtime family | Compass, GPS, barometer, and EKF integrity |
| 🔋 **Power** | runtime family | Voltage/current dynamics, sag, power, and system supply |
| 🚁 **Propulsion** | runtime family | Motor balance, output saturation, thrust, and ESC fallbacks |
| 🕹️ **Control + System** | runtime family | Attitude/rate tracking, PID signals, loop timing, and events |
| 📈 **Derived/FFT** | runtime family | Finite derived ratios and IMU-only spectral fallbacks |

All features are documented in [`models/feature_columns.json`](models/feature_columns.json).

---

## 📊 Production Benchmark Results

The benchmark below uses source-log-disjoint evaluation. Windowed samples from one flight never appear in both training and test partitions. Performance is intentionally lower than the old row-split estimate and should be treated as the current honest baseline.

The intermediate `v3_grouped` run (F1 0.559/ECE 0.158) is rejected because
two source-URL groups contain contradictory labels. The safe
`v3_unambiguous` candidate excludes those four files and is the evidence shown
below.

| Metric | Result | Target | Status |
|---|---|---|---|
| **Honest grouped candidate log Macro F1** | **0.500** | ≥ 0.70 | ⚠️ RELEASE BLOCKED |
| **Honest grouped holdout** | **23 source incidents** | ≥ 50 | ⚠️ RELEASE BLOCKED |
| **Incident-level calibration (ECE)** | **0.153** | ≤ 0.08 | ⚠️ RELEASE BLOCKED |
| **Runtime feature schema** | **111 finite features** | Exact match | ✅ PASS |
| **Regression suite** | **338 passing, 0 skipped** | All green | ✅ PASS |
| **Real-log integration** | **43/43 crash-free; 7/7 golden labels** | No crashes; expected labels present | ✅ PASS |

### CITA-Nexus Acceptance Certification

The current source-bound acceptance run certifies the following CITA-Nexus
runtime targets. Results are reported as measured; the local SITL fallback was
used when Docker was unavailable.

| Metric | Target SLA | Measured result | Status |
|---|---:|---:|---|
| **CLI import overhead** | Minimal | **3.53 ms** | ✅ PASS |
| **Cold-start diagnosis** | < 250.0 ms | **233.5 ms** | ✅ PASS |
| **Ingestion latency** | < 200.0 ms | **103.0 ms** | ✅ PASS |
| **Steady-state diagnosis** | < 250.0 ms | **69.6 ms** | ✅ PASS |
| **Peak memory allocation** | < 200.0 MiB | **162.8 MiB** | ✅ PASS |
| **Parallel batch throughput** | > 30.0 logs/s | **1,077.9 logs/s** | ✅ PASS |
| **Local SITL fallback** | > 900 logs/h | **104,426 logs/h** | ✅ PASS |
| **Comprehensive test suite** | All core tests passing | **106 passed, 1 skipped** | ✅ PASS |

The benchmark command is:

```bash
uv run --isolated --no-project --with numpy --with scipy --with pyarrow python benchmarks/acceptance.py
```

The read-only MCP surface exposes `diagnose_flight_log`, `get_causal_dag`,
and `get_param_diffs`. These tools return evidence and provenance only; they
do not write parameters or modify uploaded logs.

The trajectory visualizer is offline and self-contained. Its generated report
does not require a CDN, external JavaScript host, or network access.

### Reliability Diagram — Per-Label Calibration

<div align="center">
<img src="docs/assets/reliability_diagram.png" alt="Reliability Diagram — ArduPilot Classifier" width="800"/>

<sub>Per-label reliability curves showing confidence vs. accuracy alignment. The closer to the diagonal "Perfect" line, the more trustworthy the confidence scores are.</sub>
</div>

<br/>

### ML Model Card

| Property | Value |
|---|---|
| **Selected candidate** | RandomForest (selected by grouped log-level metric) |
| **Feature schema** | 111 runtime features |
| **Training corpus** | 114 usable source logs / 9 ML labels |
| **Holdout** | 23 independent source incidents |
| **Calibration** | Incident-level ECE 0.153; calibration gate fails and requires retraining |
| **Rules-only labels** | `brownout`, `crash_unknown`, `mechanical_failure`, `setup_error`, `thrust_loss` |
| **Anomaly detector** | Co-located artifact with exact feature schema |

See [`docs/model_card.md`](docs/model_card.md) for the full architectural breakdown.

---

## 🚀 All Usage Modes

### CLI — Command Line Interface

```bash
# Analyze a single log
python -m src.cli.main analyze flight.BIN

# Optional Betaflight/Cleanflight Blackbox support (.bbl/.bfl)
pip install -e ".[blackbox]"
python -m src.cli.main analyze flight.bbl --format json

# Inspect hardware, sensors, parameters, and log quality (read-only)
python -m src.cli.main hardware flight.BIN --format terminal

# Compare two .param files or two ArduPilot .BIN parameter snapshots
python -m src.cli.main param-diff before.param after.param --format terminal

# Validate safety-sensitive parameter ranges without writing anything
python -m src.cli.main param-validate aircraft.param --format terminal

# Export one canonical report as JSON, HTML, or PDF
python -m src.cli.main report flight.BIN --format pdf -o flight-report.pdf

# Export an offline GPS track for QGIS/Google Earth (exact coordinates; scrub before sharing)
python -m src.cli.main export flight.BIN --format gpx -o flight.gpx
python -m src.cli.main export flight.BIN --format kml -o flight.kml

# Export raw messages or a safe derived series for external analysis
python -m src.cli.main export flight.BIN --format csv --messages GPS,BARO -o flight.csv
python -m src.cli.main export flight.BIN --format parquet -o flight.parquet
python -m src.cli.main export flight.BIN --format derived-json --derived GPS.Alt-BARO.Alt -o altitude-residual.json
python -m src.cli.main export flight.BIN --format graph-pack -o flight-graphs.html
python -m src.cli.main export flight.BIN --format artifacts -o flight-artifacts

# Export manual log/video synchronization as a JSON, WebVTT, or SRT sidecar
python -m src.cli.main video-overlay flight.BIN --sync-points sync.json --format vtt -o flight.vtt

# Inspect the read-only ArduPilot parameter catalog
python -m src.cli.main params search notch
python -m src.cli.main params validate ATC_RAT_RLL_P 0.135 --format json

# Validate a QGC WPL/JSON mission, or compare it with a flown track
python -m src.cli.main mission mission.json
python -m src.cli.main mission mission.json flight.BIN --tolerance-m 30

# Review repeated coarse-location findings from local fleet reports
python -m src.cli.main fleet location --aircraft-id uav-01 --db fleet.sqlite3

# Review a Methodic Configurator step from a canonical report (read-only gate)
python -m src.cli.main methodic flight-report.json --step 8.1

# Create a privacy-scrubbed expert hand-off bundle
python -m src.cli.main report flight.BIN --format bundle -o flight-review.zip --include-log

# See which deterministic capabilities are available for each input format
python -m src.cli.main capabilities

# Show coverage and scope boundaries for every named catalogue tool
python -m src.cli.main catalogue --format json -o catalogue-coverage.json

# Find, parse, group, and compare logs in a directory without uploading them
python -m src.cli.main log-finder ./logs --format json --hash -o log-index.json

# Inspect persistence/transient evidence without changing the diagnosis
python -m src.cli.main temporal flight.BIN --no-ml -o temporal.json

# Run the transparent 44-card community checklist
python -m src.cli.main checks flight.BIN -o community-checks.json

# Run a read-only flight-test acceptance checklist
python -m src.cli.main acceptance flight.BIN --require gps_metrics --require control_metrics

# Build a known-good baseline from canonical JSON reports
python -m src.cli.main baseline reports/healthy-1.json reports/healthy-2.json -o baseline.json

# Compare canonical reports before/after maintenance
python -m src.cli.main maintenance before.json after.json

# Persist canonical reports in an operator-owned local SQLite store
python -m src.cli.main fleet add report.json --aircraft-id uav-01 --db fleet.sqlite3
python -m src.cli.main fleet trend --aircraft-id uav-01 --db fleet.sqlite3

# Run the demo on the sample log
python -m src.cli.main demo

# Launch the interactive web dashboard
python -m src.cli.main ui

# Run benchmark suite
python -m src.cli.main benchmark

# Clean-import logs (SHA256 dedup + provenance)
python -m src.cli.main import-clean \
  --source-root "/path/to/logs" \
  --output-root "data/clean_imports/my_batch"

# Mine expert labels from ArduPilot forum
python -m src.cli.main mine-expert-labels \
  --output-root data/raw_downloads/expert_batch_01 \
  --queries-json ops/expert_label_pipeline/queries/crash_analysis_high_recall.json
```

### Web API — REST Endpoint

```bash
# Start the server
python -m src.cli.main ui

# POST a .BIN/.LOG, .ULG/.ULOG, .TLOG, or (with the blackbox extra) .BBL/.BFL file for analysis
curl -X POST -F "file=@flight.BIN" http://localhost:8000/api/analyze

# Read-only hardware report and parameter comparison endpoints
curl -X POST -F "file=@flight.BIN" http://localhost:8000/api/hardware
curl -X POST -F "before=@before.param" -F "after=@after.param" \
  http://localhost:8000/api/param-diff
curl -X POST -F "file=@aircraft.param" http://localhost:8000/api/param-validate

# Offline GPX/KML track and Methodic step review from JSON payloads
curl -X POST -H "Content-Type: application/json" -d '{"parsed":{"messages":{"GPS":[]}},"format":"gpx"}' http://localhost:8000/api/track
curl -X POST -H "Content-Type: application/json" -d '{"report":{...},"step":"8.1"}' http://localhost:8000/api/methodic

# Mission validation/compliance, plots, derived series, and parameter catalog
curl -X POST -H "Content-Type: application/json" -d '{"mission":[{"seq":0,"lat":37.422,"lng":-122.084,"alt":20}]}' http://localhost:8000/api/mission/validate
curl -X POST -H "Content-Type: application/json" -d '{"report":{...},"kind":"diagnoses"}' http://localhost:8000/api/plot
curl -X POST -H "Content-Type: application/json" -d '{"report":{...},"parsed":{"messages":{"GPS":[]}}}' http://localhost:8000/api/graph-pack
curl -X POST -H "Content-Type: application/json" -d '{"parsed":{"errors":[]},"sync":{"status":"review_only","offset_sec":2}}' http://localhost:8000/api/context/video-overlay
# Add "format":"vtt" or "format":"srt" for editor-ready subtitle content
curl -X POST -H "Content-Type: application/json" -d '{"parsed":{},"diagnoses":[]}' http://localhost:8000/api/context/temporal
curl -X POST -H "Content-Type: application/json" -d '{"parsed":{}}' http://localhost:8000/api/checks/community
curl -X POST -H "Content-Type: application/json" -d '{"parsed":{"messages":{"CMD":[]}}}' http://localhost:8000/api/artifacts
curl "http://localhost:8000/api/params/search?query=notch"

# Capability registry (including generic PX4 ULog and MAVLink TLog adapters)
curl http://localhost:8000/api/capabilities
curl http://localhost:8000/api/catalogue
curl http://localhost:8000/api/tools

# Optional local fleet persistence (configure ARDUPILOT_FLEET_DB and a secret
# ARDUPILOT_FLEET_TOKEN before exposing the HTTP fleet endpoints)
# PowerShell example: $env:ARDUPILOT_FLEET_TOKEN = "paste-a-random-secret-here"
curl -X POST -H "Content-Type: application/json" \
  -d '{"aircraft_id":"uav-01","report":{...}}' \
  -H "Authorization: Bearer paste-a-random-secret-here" \
  http://localhost:8000/api/fleet/reports
curl -H "Authorization: Bearer paste-a-random-secret-here" \
  "http://localhost:8000/api/fleet/trend?aircraft_id=uav-01"

# Runtime probes and local metrics
curl http://localhost:8000/healthz
curl http://localhost:8000/readyz
curl http://localhost:8000/metrics

# Container deployment (core engine by default; optional services are review-only)
docker compose up --build
docker compose --profile experimental up --build  # temporal/grounded services

Fleet HTTP routes fail closed with `503 Fleet auth token is not configured` when
`ARDUPILOT_FLEET_TOKEN` is unset.  The same-origin dashboard does not require
CORS; a separately hosted frontend must explicitly set
`ARDUPILOT_CORS_ORIGINS` to a comma-separated origin allowlist.  Do not use a
wildcard origin with credentials.
```

The `/api/analyze` endpoint returns a structured JSON response (validated via Pydantic `AnalysisResponse` schema):

```json
{
  "metadata": { "filename": "flight.BIN", "duration": 342.5, "vehicle": "Copter" },
  "features": { "vibe_z_max": 67.8, "mag_field_range": 450, "..." : "..." },
  "diagnoses": [
    {
      "failure_type": "vibration_high",
      "confidence": 0.68,
      "evidence": ["vibe_z_max = 67.8 (threshold: 30.0)"],
      "recommendation": "Check propeller balance and motor mounts."
    }
  ],
  "timeline_events": [...],
  "explain_data": { "decision": { "status": "confirmed", "top_guess": "vibration_high" } },
  "hardware_report": {
    "schema_version": "hardware-report.v1",
    "sensors": { "gps": { "present": true }, "esc": { "present": false } },
    "safety_findings": [],
    "log_quality": { "overall_status": "good" }
  }
}
```

All hardware, safety, sensor, tuning, and control summaries are analysis-only. They never write parameters or alter the uploaded log. Every deterministic safety finding includes its check ID, onset time (when available), evidence, recommendation, and source URL.

### Python API — Programmatic Use

```python
from src.parser.bin_parser import LogParser
from src.features.pipeline import FeaturePipeline
from src.diagnosis.hybrid_engine import HybridEngine

# Parse a .BIN file
parser = LogParser("flight.BIN")
parsed = parser.parse()

# Extract the 111-feature runtime vector
pipeline = FeaturePipeline()
features = pipeline.extract(parsed)

# Run hybrid diagnosis
engine = HybridEngine()
diagnoses = engine.diagnose(features)

for d in diagnoses:
    print(f"{d['failure_type']}: {d['confidence']:.0%} ({d['detection_method']})")
    # → vibration_high: 68% (rule+ml)
```

---

## 🔬 Data Pipeline & Training

### Training a New Model

```bash
# Build the dataset from labeled logs
python training/build_dataset.py --min-confidence medium

# Train the classifier + anomaly detector
python training/train_model.py

# Validate zero leakage between train/holdout
python validate_leakage.py
```

### Clean Import (Production-Safe Ingestion)

Applies strict SHA256 dedup, non-log rejection, provenance proof, and benchmark-ready export:

```bash
python -m src.cli.main import-clean \
  --source-root "/path/to/downloaded/logs" \
  --output-root "data/clean_imports/my_batch"
```

Produces: `source_inventory.csv`, `clean_import_manifest.csv`, `rejected_manifest.csv`, `provenance_proof.md`, `ground_truth.json`.

### Running Benchmarks

```bash
# Auto-discovers latest clean-imported benchmark subset
python -m src.cli.main benchmark

# Against a specific holdout set
python -m src.cli.main benchmark \
  --dataset-dir data/holdouts/production_holdout_clean/dataset \
  --ground-truth data/holdouts/production_holdout_clean/ground_truth.json
```

---

## ☁️ Cloud Execution

### GitHub Codespaces

1. Open the repo → **Code → Codespaces → Create codespace on main**.
2. Container setup completes automatically via `.devcontainer/devcontainer.json`.
3. Run any command in the integrated terminal.

### Google Colab

```bash
# 1. Create a portable data bundle locally
python training/create_colab_bundle.py \
  --output colab_data_bundle.tar.gz \
  --paths data/final_training_dataset_2026-02-23

# 2. In Colab — clone repo, install requirements, extract bundle, then:
python training/run_all_benchmarks.py \
  --dataset-dir data/final_training_dataset_2026-02-23/dataset \
  --ground-truth data/final_training_dataset_2026-02-23/ground_truth.json
```

See [Colab Quickstart](docs/colab_quickstart.md) · [Kaggle Quickstart](docs/kaggle_quickstart.md) for full walkthroughs.

---

## 🔧 Recent Audit & Fixes (March 2026)

A comprehensive forensic audit was performed across the entire codebase. Below are the issues identified and resolved:

### 🔴 Critical Fixes (Execution Blockers)

| # | Issue | Resolution |
|---|---|---|
| 1 | **pydantic version conflict** — `pydantic-core` 2.43.0 incompatible with `pydantic` 2.12.5, **all** tests blocked | Resolved: `pip install --upgrade pydantic pydantic-core langsmith` aligned versions to `pydantic-core==2.41.5` |
| 2 | **mavlogdump.py invocation broken on Windows** — `subprocess.run(["mavlogdump.py", ...])` → `FileNotFoundError` | Fixed: Changed to `[sys.executable, "-m", "pymavlink.tools.mavlogdump", ...]` for cross-platform compatibility |
| 3 | **Web API test failure** — `test_api_analyze_handles_gps_without_vibe` crashed with `'AnalysisResponse' has no attribute 'body'` | Fixed: Updated test helpers to handle both `JSONResponse` (error) and `AnalysisResponse` (pydantic model) return types |

### 🟠 Major Improvements (Bug Prevention)

| # | Issue | Resolution |
|---|---|---|
| 4 | **Hardcoded import paths** — `import_basic_direct.py` used `C:\Downloads\...` | Fixed: Changed to `Path.home() / "Downloads"` for portability |
| 5 | **Missing directory safety** — `validate_leakage.py` would crash if data dirs don't exist | Fixed: Added existence checks before `os.walk()` |
| 6 | **Silent subprocess errors** — `hybrid_system.py` only printed `stdout`, `stderr` swallowed | Fixed: All phases now print `result.stderr` for debugging |
| 7 | **Bare `except` clause** — `download_manager.py` caught everything including `KeyboardInterrupt` | Fixed: Narrowed to `except (requests.RequestException, ValueError, KeyError)` |

### Post-Audit Verification

```
$ python -m pytest tests/ -q
338 passed, 0 skipped ✅

$ python /tmp/e2e_test.py
Diagnoses: 1
  vibration_high: <confidence varies by log> (rule+ml)
Anomaly detected: True
Features extracted: 111 ✅
```

---

## 📁 Project Structure

```
ardupilot-log-diagnosis/
├── src/
│   ├── parser/              # pymavlink .BIN log decoder
│   │   └── bin_parser.py    #   → 24,837 messages from sample.bin
│   ├── features/            # 111-feature extraction pipeline
│   │   ├── pipeline.py      #   → orchestrates all extractors
│   │   └── extractors/      #   → vibration, compass, GPS, EKF, motors, power, control, events, FFT
│   ├── diagnosis/           # Hybrid diagnostic engine
│   │   ├── hybrid_engine.py #   → fuses rule + ML + anomaly signals
│   │   ├── rule_engine.py   #   → 13 deterministic threshold checks
│   │   ├── ml_classifier.py #   → schema-checked ML inference with safe abstention
│   │   ├── anomaly_detector.py # → IsolationForest for unknown failures
│   │   ├── decision_policy.py  # → CITA temporal arbitration
│   │   └── rules/           #   → individual rule check modules
│   ├── cli/                 # CLI entry point: `python -m src.cli.main`
│   │   └── commands/        #   → analyze, benchmark, demo, import, mine, ui
│   ├── web/                 # FastAPI dashboard + REST API
│   │   ├── app.py           #   → /api/analyze endpoint
│   │   ├── schemas.py       #   → pydantic AnalysisResponse model
│   │   └── index.html       #   → 800+ line interactive UI
│   ├── constants.py         # Feature names, thresholds, label taxonomy
│   ├── contracts.py         # TypedDict schemas for type safety
│   └── runtime_paths.py     # Dynamic model directory resolution
├── models/                  # Versioned ML artifacts
│   ├── classifier.joblib    #   → versioned candidate/legacy model artifact
│   ├── scaler.joblib        #   → StandardScaler
│   ├── anomaly_detector.joblib # → IsolationForest
│   ├── feature_columns.json #   → artifact feature schema
│   ├── label_columns.json   #   → 6-label schema
│   └── manifest.json        #   → version + hash integrity
├── training/                # Dataset build + training pipeline
│   ├── train_model.py       #   → grouped candidate training + artifact manifests
│   ├── build_dataset.py     #   → feature extraction from labeled logs
│   └── import_basic_direct.py # → BASiC Zenodo dataset importer
├── tests/                   # 338 tests (parser, features, diagnosis, web, exports, contracts)
├── docs/                    # Architecture, GSoC proposal, model card, policies
│   └── assets/              #   → screenshots and diagrams
├── ops/                     # Expert label mining pipeline
├── bootstrap.sh             # One-click setup script
├── pyproject.toml           # Package config + dependencies
├── sample.bin               # Real ArduPilot log for testing
└── CHANGELOG.md             # Full version history
```

---

## 🚀 GSoC 2026: The 12-Week Roadmap

The diagnostic engine is proven. **GSoC transforms it from a developer tool into a live-flight safety system.**

| Phase | Weeks | Deliverable | Impact |
|---|---|---|---|
| **Upstream Integration** | W1–W3 | Refactor engine to ArduPilot MAVExplorer plugin standards; submit PR | Official tool in ArduPilot ecosystem |
| **Dataset Scale-Up** | W3–W5 | Expert Label Mining: 140 → 500+ labeled logs | Statistically robust across all vehicle types |
| **Live MAVLink Streaming** | W5–W7 | Real-time diagnostics from live telemetry streams | **First open-source tool to diagnose during flight** |
| **Edge Inference (C++)** | W8–W10 | Port to companion computer (Raspberry Pi, Jetson Nano) | On-board pre-flight safety checks in < 100ms |
| **Community Platform** | W11–W12 | Web portal for crowdsourced log submission + labeling | Permanent, growing ecosystem resource |

See [`docs/GSOC_2026_Application.md`](docs/GSOC_2026_Application.md) for the complete application.

---

## 🔒 Data Integrity & Labeling Policy

Data integrity is a first-class constraint:

1. **Earliest Onset Wins**: The feature with the earliest `t_anomaly` is the root cause — not whatever label the forum post used.
2. **Sequential Causal Chains**: If A caused B, the label is A.
3. **Temporal Tie-Break**: Within 5s, highest rule-confidence score wins.
4. **Zero Leakage Enforced**: `validate_leakage.py` performs SHA256 cross-checks across all train/holdout splits.

See [`docs/PRODUCTION_ACCEPTANCE_CRITERIA.md`](docs/PRODUCTION_ACCEPTANCE_CRITERIA.md) and [`docs/root_cause_policy.md`](docs/root_cause_policy.md).

---

## 📄 Key Documents

| Document | Description |
|---|---|
| [`docs/GSOC_2026_Application.md`](docs/GSOC_2026_Application.md) | Full GSoC 2026 application |
| [`docs/model_card.md`](docs/model_card.md) | Technical ML specs and calibration report |
| [`docs/root_cause_policy.md`](docs/root_cause_policy.md) | CITA temporal arbitration specification |
| [`docs/PRODUCTION_ACCEPTANCE_CRITERIA.md`](docs/PRODUCTION_ACCEPTANCE_CRITERIA.md) | Release gates & labeling policy |
| [`docs/MAINTAINER_TRIAGE_REDUX.md`](docs/MAINTAINER_TRIAGE_REDUX.md) | Triage impact study (98% time reduction) |
| [`docs/DATA_PROVENANCE.md`](docs/DATA_PROVENANCE.md) | Full dataset lineage and provenance tracking |
| [`docs/UPGRADE_ROADMAP.md`](docs/UPGRADE_ROADMAP.md) | Technical roadmap and future improvements |
| [`CHANGELOG.md`](CHANGELOG.md) | Complete version history |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | How to contribute crash logs or rules |

---

## 🤝 Contributing

We welcome contributions! Here's how:

### Submit Crash Logs
If you have ArduPilot `.BIN` logs from real flights (especially crashes!), they are invaluable for improving the model. See [`CONTRIBUTING.md`](CONTRIBUTING.md).

### Add Diagnosis Rules
Create a new check function in `src/diagnosis/rules/` following the existing pattern. Each rule takes `(features, thresholds)` and returns `DiagnosisDict | None`.

### AI Contributor Workflow
Agents working on this repository must follow [`docs/AI_CONTRIBUTOR_GUIDE.md`](docs/AI_CONTRIBUTOR_GUIDE.md), including provenance checks, grouped evaluation, abstention boundaries, and the full verification commands.

### Report Issues
Open a GitHub issue with your `.BIN` file (or a sanitized version) and what you expected the diagnosis to be.

---

## 🎯 Open Issues & AI Contributor Hand-off

Current release blockers are tracked in [`docs/PRODUCTION_READINESS.md`](docs/PRODUCTION_READINESS.md):

1. The safe honest 111-feature candidate scores 0.500 grouped log-level Macro F1 (gate: 0.700); a 0.559 intermediate run was rejected for contradictory incident labels.
2. The frozen grouped holdout contains 23 source incidents (gate: 50).
3. Five labels remain rules-only until independently expert-labelled logs are available.
4. Fourteen capabilities are review-only and two are experimental; their status is exposed through `/api/capabilities` and the CLI capability registry.
5. Provisional forum/search labels must not be merged into training without expert provenance.

The runtime, API, adapters, security controls, and regression suite are maintained as production-hardened components while those evidence gates remain open.

---

## 📜 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

<div align="center">

**Built with ❤️ for the ArduPilot community**

*By [Agastya Pandey](https://github.com/BeastAyyG) — SRM University AP*

*ArduPilot AI Log Diagnosis · GSoC 2026*

</div>
