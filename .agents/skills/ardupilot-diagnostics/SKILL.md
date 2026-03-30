---
name: ardupilot-diagnostics
description: Diagnose ArduPilot .BIN flight logs to determine the root cause of crashes or failures using the Hybrid AI Engine.
risk: safe
source: "ArduPilot GSoC 2026 Project (MIT)"
date_added: "2026-03-30"
---

# ArduPilot Log Diagnostics Skill

## Overview
This skill grants an AI agent the ability to autonomously diagnose ArduPilot `.BIN` flight telemetry logs. Instead of manually inspecting graphs or MAVLink messages, the agent can feed the log into the **Hybrid Causal Arbiter** (Rule Engine + XGBoost ML) to extract the primary failure reason, 3D trajectory evidence, and actionable maintenance recommendations.

## When to Use This Skill
- When a user provides a `.BIN` file and asks "Why did my drone crash?"
- When analyzing flight performance degradation (e.g., high vibrations, compass interference).
- When generating a post-flight maintenance report for a fleet of autonomous vehicles.

## Prerequisites
- The system must have the `ardupilot-log-diagnosis` Python environment active.
- The `.BIN` file must be accessible on the local filesystem.

## Workflow Instructions

### 1. Execute the Diagnostic Engine CLI
To analyze a `.BIN` file, execute the built-in command-line interface:
```bash
python -m src.cli.main analyze /path/to/flight.bin
```

### 2. Parse the output
Read the resulting JSON or terminal output carefully. You must extract:
- **Decision:** (Healthy, Warning, or Critical Crash)
- **Top Root Cause:** (e.g., Compass Interference, Motor Imbalance, EKF Failsafe)
- **Confidence/ECE:** State the ML calibration confidence mathematically (e.g., F1 1.0, 99.8% confident).
- **Evidence:** Which specific parameters/thresholds were violated?
- **Recommendations:** What physical repairs or tuning steps should the pilot take?

### 3. Present the Findings
Do not dump raw JSON logic to the user. Synthesize a professional Drone Mechanic Report:
1.  **Summary:** Briefly explain what happened to the vehicle.
2.  **Causal Chain:** Detail the timeline of the failure (if available).
3.  **Prescription:** Give the user the exact steps to prevent this in the future.

## Failure Shields (Important)
- If the tool reports an unknown file parsing error, inform the user that their `.BIN` file may be corrupted or truncated mid-air.
- If the tool falls back to the **Rule Engine Only**, inform the user that the ML model abstained due to low confidence on this specific edge case in order to preserve diagnostic integrity.
