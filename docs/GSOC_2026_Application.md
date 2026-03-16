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
1. **Feature Extraction Pipeline:** Translates raw ArduPilot telemetry (IMU, EKF, GPS, MOT, BAT) into over 150 meaningful statistical features suitable for ML models.
2. **Hybrid Diagnostic Engine:** Combines threshold-based telemetry rules with a calibrated XGBoost/Random Forest model. Priority is given to verified community knowledge.
3. **Training Dataset & Provenance:** Establishing maintaining a 100+ flight log `.BIN` dataset, explicitly tying each log to its `discuss.ardupilot.org` thread to guarantee label integrity. Currently covers 9 failure categories including `motor_imbalance`, `compass_interference`, `ekf_failure`, and `vibration_high`.
4. **Integration Ready Engine:** A CLI-tool wrapper allowing maintainers to run `analyze <log.bin>` to get near-instant confidence scores on exactly *why* a drone crashed.

## 3. Why am I the right person for this project?
As an AI & ML student at SRM University AP, I have spent the last several months independently developing a working prototype of this diagnostic engine — before GSoC applications opened. This is not a proposal-stage idea; it is running code with 162 passing tests.

What I've built so far:
- A complete `.BIN` → features → rule engine → ML → hybrid fusion pipeline with a working CLI.
- A physics-based rule engine covering 13 failure check modules (vibration, compass, EKF, GPS, motors, power, RC, PID, mechanical failure, thrust loss, setup errors, system events).
- A temporal causal arbiter that identifies root causes and suppresses downstream symptom spam.
- SHA256-verified data provenance with zero train/holdout leakage.
- 162 passing pytest tests covering parser, features, diagnosis, contracts, and integration.

What is working well:
- Compass interference recall: 90%, Vibration recall: 85%, EKF F1: 0.67
- Triage time reduced from ~25 min to ~4 min (84% reduction) on 20-case study.

What I'm honest about:
- Macro F1 is 0.357 — the ML model needs more labeled data to generalize beyond vibration/compass.
- Motor imbalance (F1=0.15), power instability (F1=0.00), PID tuning (F1=0.00) are undertrained.
- The holdout set is only 45 logs — statistically thin. Expanding to 500+ is the core GSoC goal.

## 4. Timeline
**Community Bonding (May 2026):**
- Finalize discussions with mentors on the ideal output format for maintainers.
- Gather feedback on the existing Data Provenance tracking format and label classes.
- Post project introduction on discuss.ardupilot.org and gather community crash logs.

**Phase 1 (June 2026): Dataset Expansion & Pipeline Hardening**
- Expand labeled dataset from 45 to 200+ logs using expert label mining pipeline.
- Improve minority-class coverage (motor_imbalance, power_instability, pid_tuning, rc_failsafe).
- Submit Data Provenance documentation PR to ArduPilot documentation repository.

**Phase 2 (July 2026): Diagnoser Engine Tuning**
- Fine-tune the Hybrid Engine's temporal arbiter and cascading logic to ensure the model distinguishes accurately between *symptoms* (like flyaways) and *root causes* (like compass magnetic interference).
- Benchmark the rule + ML models against a strict blind holdout set.
- Target: Macro F1 from 0.357 → 0.70+ with expanded data.

**Phase 3 (August 2026): Polishing, Packaging & Final Evaluation**
- Freeze the hybrid model architecture and export production-ready `.joblib` weights.
- Improve CLI user experience (UX) and add HTML/Markdown report generation for forum pasting.
- Submit the engine as an official ArduPilot tool.
- Final benchmark on 500+ log holdout set.

## 5. Summary of Prior Work
- Open Source Repo: [BeastAyyG/ardupilot-log-diagnosis](https://github.com/BeastAyyG/ardupilot-log-diagnosis)
- 162 passing tests, full CI pipeline, devcontainer support, comprehensive documentation.
- I have fixed critical data parsing bugs, integrated SMOTE for handling class imbalances, and mapped every log in the dataset back to its original forum incident so labels are fully verifiable by ArduPilot domain experts.

## 6. Known Limitations & Improvement Plan
| Current Limitation | GSoC Improvement Target |
|---|---|
| Macro F1 = 0.357 | Target ≥ 0.70 with 500+ logs |
| Motor imbalance F1 = 0.15 | Dedicated motor RPM/current rules + more labeled data |
| Power instability F1 = 0.00 | Voltage sag pattern detection + power module-specific rules |
| PID tuning F1 = 0.00 | PID saturation counter analysis + oscillation frequency detection |
| 45-log holdout (thin) | Expand to 500+ with community-sourced logs |

