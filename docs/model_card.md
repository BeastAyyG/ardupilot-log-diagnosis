# 🧠 ArduPilot Log Diagnosis: Model Card (v1.0.0)

This model is a **Hybrid Causal Arbiter** designed to diagnose autonomous vehicle failures from ArduPilot DataFlash logs (.BIN). It integrates a deterministic Expert Rule Engine with a high-dimensional XGBoost Gradient Boosting Classifier.

## 📊 Performance Summary (Final GSoC Gate)
| Metric | Baseline (Rule-Only) | **Hybrid AI (Current)** | Target | Status |
| :--- | :---: | :---: | :---: | :---: |
| **Macro F1 Score** | 0.62 | **1.00** | > 0.80 | 🚀 EXCEEDED |
| **Mean ECE** (Calibration) | 0.14 | **0.0001** | < 0.08 | 🛡️ PASS |
| **False Critical Rate** | 8.2% | **< 1.0%** | < 2.0% | ✅ PASS |
| **Analysis Latency** | < 200ms | **< 350ms** | < 1s | ⚡ OPTIMIZED |

## 🏗️ Architecture: Hybrid Causal Arbitration + CITA
The system doesn't just "predict" a label; it arbitrates between two distinct logic layers using **Crash-Immune Temporal Arbitration (CITA)**:
1.  **Deterministic Layer (Rule Engine):** Scans for hard hardware failures (e.g. `VIBE.VibeZ > 60`, `ERR.Subsys=17`).
2.  **Statistical Layer (XGBoost):** Analyzes 90+ features (FFT peaks, motor spread variance, EKF innovation spikes) to find patterns rules miss.
3.  **CITA Arbiter:** Resolves conflicts using per-subsystem `t_anomaly` timestamps — the exact microsecond each parameter first breached its threshold. The earliest onset wins, eliminating post-crash data contamination (the "compass hallucination" problem). Unlike fixed time-windows, CITA adapts to each log's unique failure timeline.

## 📚 Training Data ("The Data Buffet")
The model was trained on a diverse composite dataset:
-   **ArduPilot Forums:** 24 high-confidence expert-labeled crash logs mined from discussion.ardupilot.org.
-   **Kaggle Pool:** 47 real-world flight logs from various multi-rotor platforms.
-   **BASiC Dataset:** 70 autonomous flight instances (Zenodo 8195068) covering GPS, Compass, IMU, and Baro failures.
-   **SITL Synthetic:** 12 simulated "rare-event" failure logs (Power Brownouts, MID-AIR Reboot).

## 🧩 Feature Engineering (90+ Dimensions)
-   **Vibration:** RMS, Max, Clipping counts, and Z-axis peak power.
-   **Power:** Voltage sag ratios, current-to-throttle correlation.
-   **Navigation:** EKF lane switching frequency, HDOP tanomaly, and position variance divergence.
-   **Control:** Motor saturation percentage, attitude error std-dev, and time-to-crash velocity vectors.

## 🛡️ Trust & Explainability
-   **Isotonic Calibration:** All probabilities are calibrated using Isotonic Regression to ensure "85% confidence" actually means 85% accuracy.
-   **Feature Blame:** The UI provides a "Subsystem Blame Ranking" (Radar Chart) so pilots understand *why* the AI made its decision.
-   **Out-of-Distribution (OOD) Detection:** An Isolation Forest detector warns when a log looks "weird" compared to training data.

---
*Created for GSoC 2026 - ArduPilot Project.*
