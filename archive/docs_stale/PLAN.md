# ArduPilot Log Diagnosis Project Plan

## Phase 1: Feature Engineering (DONE locally)
- [x] Enhance `base_extractor.py` with temporal tracing (`tanomaly`).
- [x] Integrate `tanomaly` into `Vibration`, `Compass`, `Power`, `GPS`, `Motors`, and `EKF` extractors.
- [x] Add aligned thresholds for anomaly detection.

## Phase 2: Meta-Learner (Kaggle Hybrid Engine)
- [x] Integrate Temporal Arbiter into `HybridEngine`.
- [x] Implement root-cause disambiguation (priority to earliest symptom).
- [ ] Train XGBoost/CatBoost meta-learner on extracted features (Phase 4 integration).

## Phase 3: Benchmark & Pipeline Integration (IN PROGRESS)
- [x] Optimize `LogParser` for memory and speed.
- [x] Disable expensive manual FFT to prevent hangs.
- [ ] Run full benchmark suite on Kaggle to verify accuracy improvements.
- [ ] Integrate full hybrid engine (Rules + ML) with Arbiter filter.

## Phase 4: Data Mining & Iteration
- [x] Collect new logs from ArduPilot forum.
- [x] Optimize data and perform cleanups (deduplication, deduplication, parsing validation).
- [ ] Label logs using the high-confidence rules + manual review.
- [ ] Retrain and improve Arbiter.

## Data Integrity Constraints
*   **NO FABRICATED DATA**. Only real flight logs.
*   Document every modification.
*   Prioritize provenance (Forum URL, log SHA).
