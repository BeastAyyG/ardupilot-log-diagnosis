# ArduPilot GSoC 2026 Application: AI Log Diagnosis System

**Full Legal Name:** Agastya Pandey (B.Tech Student)  
**Email:** agastya_pandey@srmap.edu.in  
**University Name:** SRM University AP  
**Degree and Year:** B.Tech in Computer Science and Engineering (AI & ML), 1st Year (2nd Semester)  
**Phone Number:** +91 8755546692  
**Documentation PR Link:** *(TODO: Open a PR to ArduPilot docs repo and paste URL here before submission)*  
**Forum Pre-application Thread Link:** *(TODO: Post introduction on discuss.ardupilot.org and paste URL here before submission)*  
**Exam Dates:** May 19–30, 2026 (End-semester exams, SRM University AP). Reduced availability during this window (~15 hrs/week instead of 35+).  
**Summer Availability:** Full-time availability from June 1 through August 31, 2026 (35+ hrs/week).  

---

## 1. Project Title
**ArduPilot AI Data Log Diagnosis: Machine Learning Pipeline for Automated Crash Analysis**

## 2. Project Description
Analyzing ArduPilot `.BIN` flight logs after a crash is a highly manual, time-consuming process that requires deep domain expertise. Maintainers and community experts spend countless hours deciphering parameter spikes, vibration frequencies, and EKF variance to diagnose if a crash was a hardware failure, tuning issue, or compass interference.

This project implements an open-source, hybrid automated diagnosis engine. By combining a deterministic rule-based engine (evaluating ArduPilot telemetry against known safety thresholds) with a machine learning model (trained on extracted feature vectors from historical `.BIN` logs), the system provides instant, high-confidence root-cause analysis for flight failures.

### Key Deliverables:
1. **Interactive 3D Mission Replay UI:** A Vue/Plotly-based dashboard that visualizes crash trajectory, vibration patterns, and causality events in a single view.
2. **Feature Extraction Pipeline:** Translates raw ArduPilot telemetry (IMU, EKF, GPS, MOT, BAT) into 94 statistical and temporal features suitable for ML models.
3. **Hybrid Diagnostic Engine & Anomaly Detector:** Combines deterministic telemetry rules with a sigmoid-calibrated XGBoost model and an Isolation Forest for out-of-distribution warnings.
4. **Training Dataset & Provenance:** Rebuilt a SHA-deduplicated feature table of 114 unique flights and a separate 24-log human review queue, of which 2 candidates were promoted on the July 24 audit, with group-isolated holdout evaluation.
5. **Integration Ready Engine:** A CLI and Web tool wrapper allowing maintainers to get near-instant confidence scores on exactly *why* a drone crashed.

## 3. Why am I the right person for this project?
As an AI & ML student at SRM University AP, I have spent the last several months independently developing a working prototype of this diagnostic engine — before GSoC applications opened. This is not a proposal-stage idea; it is running code with 219 passing tests.

What I've built so far:
- **Vehicle-Aware Ingestion**: Dynamic routing that identifies Copter vs Plane vs Rover vs Sub from boot text and `FRAME_CLASS`, safely enabling/disabling appropriate telemetry rules.
- **Hypothesis Scaffolding & CITA**: The engine no longer acts like a "magic 8-ball". It outputs a transparent, temporal reasoning trace using Crash-Immune Temporal Arbitration to rank physical root causes over downstream symptoms (solving the compass hallucination problem).
- **True Thrust-Loss Detection**: Scans for sustained, synchronous `RCOU` motor saturation coupled with GPS/CTUN altitude descent.
- **Pre-Flight Parameter Validation**: Evaluates `PARM` values (e.g. default PIDs) against `VIBE` and attitude symptoms, flagging likely tuning issues prior to hardware failure.
- **3D Mission Replay Dashboard**: A premium interactive UI with 3D flight path reconstruction and causality markers.
- **Leakage-Controlled Dataset**: 114 unique feature rows with zero exact duplicate feature vectors. The deployed artifact preserves its locked 88/22 group-isolated split from the prior 110-eligible-flight snapshot.
- **219 passing tests** covering parser, feature routing, diagnosis, parameter validation, leakage controls, calibration, and causal arbitration.

What is working well:
- **Calibrated macro F1: 0.603** on a 22-flight, group-isolated holdout.
- **Calibration (top-label ECE): 0.1268**, which currently fails the ≤ 0.08 gate; ML probabilities remain advisory.
- **94 telemetry features** extracted with physics evidence and temporal onset metadata.
- **Eight ML-eligible failure families**, with known low-support weaknesses in motor and power failures.

Next Ambition:
- Expanding from "Retrospective Analysis" to "Real-time Edge Ingestion."
- Scaling the dataset further to 1000+ logs for deep-learning exploration.

## 4. Timeline
**Community Bonding (May 2026):**
- Finalize discussions with mentors on the ideal output format for maintainers.
- Gather feedback on the existing Data Provenance tracking format and label classes.
- Post project introduction on discuss.ardupilot.org and gather community crash logs.

**Phase 1 (June 2026): Upstream Integration & Code Standards**
- Refactor the completed Python engine to meet ArduPilot's MAVExplorer / MAVProxy plugin standards.
- PR the Hybrid Engine as an optional diagnosis module for ArduPilot's official log analysis toolchain.
- Submit Data Provenance documentation PR to ArduPilot documentation repository.

**Phase 2 (July 2026): Edge-AI & Companion Computer Porting**
- Port the lightweight XGBoost model and Rule Engine to C++ or Cython to run on companion computers (e.g. Raspberry Pi / Jetson).
- Implement real-time live telemetry ingestion via MAVLink stream instead of post-flight `.BIN` analysis.
- Target: Run diagnostic inference loops on edge hardware in < 100ms.

**Phase 3 (August 2026): Polishing, Packaging & Final Evaluation**
- Freeze the hybrid model architecture and export production-ready `.joblib` weights.
- Improve CLI user experience (UX) and add HTML/Markdown report generation for forum pasting.
- Submit the engine as an official ArduPilot tool.
- Final benchmark on 500+ log holdout set.

## 5. Summary of Prior Work
- Open Source Repo: [BeastAyyG/ardupilot-log-diagnosis](https://github.com/BeastAyyG/ardupilot-log-diagnosis)
- 219 passing tests, full CI pipeline, devcontainer support, and explicit model/data integrity checks.
- I have fixed critical data parsing bugs, integrated SMOTE for handling class imbalances, and mapped every log in the dataset back to its original forum incident so labels are fully verifiable by ArduPilot domain experts.

## 6. Known Limitations & Edge-AI Improvement Plan
| Current Final State | GSoC Future Target |
|---|---|
| Macro F1 = 0.603; ECE gate still open | Improve calibration and validate on a larger locked holdout |
| Motor imbalance detection relies on offline processing | Real-time FFT processing on Edge hardware |
| Heavy Python dependencies (Pandas, Scikit) | Port inference engine to C++ for companion computers |
| 114 unique feature rows; class imbalance remains | Expand with expert-verified, provenance-tracked community logs |

