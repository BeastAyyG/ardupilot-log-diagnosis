---
name: ardupilot-diagnostics
description: Diagnose ArduPilot .BIN flight logs to determine the root cause of crashes or failures using the Hybrid AI Engine.
risk: safe
source: "ArduPilot GSoC 2026 Project (MIT)"
date_added: "2026-03-30"
---

# ArduPilot Log Diagnostics Skill

## Overview
This skill grants an AI agent the ability to autonomously diagnose ArduPilot `.BIN` flight telemetry logs. Instead of manually inspecting graphs or MAVLink messages, the agent can feed the log into the **Hybrid Causal Arbiter** (rule engine + RandomForest ML) to get a ranked triage hypothesis with evidence and maintenance recommendations.

**Honest limits (tell the user):** on the reproducible real-log benchmark, the ML candidate does not beat chance (incident-grouped macro-F1 about 0.09 vs 0.10 chance), and it fails its release gates (see `docs/model_card.md` and `CORRECTIONS.md`). Its output is a triage hypothesis for a human to check, not a verified root cause.

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
- **Confidence:** Report the tool's confidence and decision status (`confirmed` / `uncertain`) exactly as given. Say that confidence scores are not calibrated (incident ECE 0.153). Never state an accuracy or F1 figure beyond the model card's.
- **Evidence:** Which specific parameters/thresholds were violated?
- **Recommendations:** What physical repairs or tuning steps should the pilot take?

### 3. Present the Findings
Do not dump raw JSON logic to the user. Write a concise report:
1.  **Summary:** Briefly explain what happened to the vehicle.
2.  **Causal Chain:** Detail the timeline of the failure (if available).
3.  **Next checks:** Give the tool's recommended checks, framed as things to inspect, not certain fixes.
4.  **Uncertainty:** If the status is `uncertain` or requires human review, say so first.

## Failure Shields (Important)
- If the tool reports an unknown file parsing error, inform the user that their `.BIN` file may be corrupted or truncated mid-air.
- If the tool falls back to the **Rule Engine Only**, inform the user that the ML model abstained due to low confidence on this specific edge case in order to preserve diagnostic integrity.
