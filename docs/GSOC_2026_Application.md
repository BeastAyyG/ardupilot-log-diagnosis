# ArduPilot GSoC 2026 Application: AI Log Diagnosis System

**Full Legal Name:** Agastya Pandey (B.Tech Student)  
**Email:** agastya_pandey@srmap.edu.in  
**University Name:** SRM University AP  
**Degree and Year:** B.Tech in Computer Science and Engineering (AI & ML), 1st Year (2nd Semester)  
**Phone Number:** +91 8755546692  
**Documentation PR Link:** *(Will insert when PR is opened)*  
**Forum Pre-application Thread Link:** *(Will insert when Discourse thread is posted)*  
**Exam Dates:** *(Mid-late May 2026 — exact dates pending university schedule)*  
**Summer Availability:** Available from the conclusion of the second-semester exams (typically late May) through August 2026.  

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
As an AI & ML student, I have spent the last several months independently developing a working prototype of this diagnostic engine. 
- I have built the parser, feature extraction pipeline, and SMOTE-based training scripts running against a curated Kaggle dataset of ArduPilot `.BIN` files (4.9 GB+ processed). 
- I successfully improved the model's F1 Macro score to 0.357 against unseen holdout logs, specifically diagnosing `motor_imbalance` and `compass_interference` with >85% confidence. 
- I have thoroughly documented the data provenance mapping over 111 raw flight logs back to 41 original community discussion threads, proving my dedication to data transparency and ArduPilot's open-source values.

## 4. Timeline
**Community Bonding (May 2026):**
- Finalize discussions with mentors on the ideal output format for maintainers.
- Gather feedback on the existing Data Provenance tracking format and label classes.

**Phase 1 (June 2026): Dataset Expansion & Pipeline Hardening**
- Release a formalized version of the Kaggle dataset. 
- Implement an automated "expert review" workflow to integrate new unlabeled logs (like `oscillation_crash` and `flyaway`) into active failure classes.
- Submit Data Provenance documentation PR to ArduPilot master documentation repository.

**Phase 2 (July 2026): Diagnoser Engine Tuning**
- Fine-tune the Hybrid Engine's temporal arbiter and cascading logic to ensure the model distinguishes accurately between *symptoms* (like flyaways) and *root causes* (like compass magnetic interference).
- Benchmark the rule + ML models against a strict blind holdout set.

**Phase 3 (August 2026): Polishing, Packaging & Final Evaluation**
- Freeze the hybrid model architecture and export production-ready `.joblib` weights.
- Improve CLI user experience (UX) and add HTML/Markdown report generation for forum pasting.
- Submit the engine as an official ArduPilot tool.

## 5. Summary of Prior Work
- Open Source Repo: [BeastAyyG/ardupilot-log-diagnosis](https://github.com/BeastAyyG/ardupilot-log-diagnosis)
- I have fixed critical data parsing bugs, integrated SMOTE for handling class imbalances, and mapped every log in the dataset back to its original forum incident so labels are fully verifiable by ArduPilot domain experts.
