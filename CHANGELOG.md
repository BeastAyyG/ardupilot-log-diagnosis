# Changelog

All notable changes to ArduPilot AI Log Diagnosis are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [1.0.0] — 2026-02-28 — Production Sign-Off

### Summary
Production sign-off achieved. Hybrid Rule + XGBoost engine validated on a SHA-deduplicated, zero-leakage unseen holdout set of 45 expert-labeled flight logs. Triage study completed: **242× faster** per-log analysis vs. manual maintainer review (2.1 sec vs 8.5 min average).

### Added
- **Root-cause arbitration engine** (`src/diagnosis/decision_policy.py`): implements Root-Cause Precedence policy — earliest telemetry anomaly suppresses downstream symptoms.
- **Causal cascade suppression**: `vibration_high` → `ekf_failure` cascades are now correctly attributed to the root cause, not the symptom.
- **SHA256 holdout integrity check** (`validate_leakage.py`): cross-validates all train/holdout file hashes before any benchmark run.
- **Expert label mining pipeline** (`ops/expert_label_pipeline/`): mines ArduPilot discussion forum for Developer/staff diagnosis text with zero manual labeling.
- **Unseen holdout builder** (`training/create_unseen_holdout.py`): constructs rigorously isolated evaluation splits.
- **Progress showcase generator** (`training/generate_progress_showcase.py`): produces mentor-ready benchmark reports with integrity attestation.
- **56 passing tests** covering parser, features, diagnosis, CLI, and integration contracts.
- **Production Acceptance Criteria doc** (`docs/PRODUCTION_ACCEPTANCE_CRITERIA.md`): formalises release gates, labeling policy, and holdout strategy.
- **Maintainer Triage Study** (`docs/MAINTAINER_TRIAGE_REDUX.md`): documents P4-02 impact claim with before/after triage measurements.

### Changed
- Benchmark results updated to reflect 45-log holdout run (from 10-log v0.1.0 pilot).
- Hybrid engine now outperforms rule-only baseline by confirmed margin.
- CI workflow (`ci.yml`) extended to run `validate_project_boundaries.py` before pytest.
- Ground-truth metadata schema aligned to Root-Cause Precedence policy — historical "EKF Failure" labels audited and relabeled where vibration data showed prior 80 m/s² peaks.

### Fixed
- Parser message retention for `IMU`, `POWR`, `RCIN` messages required by advanced extractors.
- Feature schema parity drift between `FeaturePipeline`, `FEATURE_NAMES` constants, and model artifacts.
- Threshold key alignment between `models/rule_thresholds.yaml` and rule engine code.

---

## [0.2.0] — 2026-02-22 — Hybrid Engine + Calibration

### Added
- XGBoost multi-label classifier training pipeline (`training/build_dataset.py`).
- Confidence calibration and abstention logic: low-confidence cases surface a `UNCERTAIN — HUMAN REVIEW` state.
- Evidence schema standardisation: every diagnosis now carries `feature / value / threshold / context` structured evidence.
- Recommendation schema standardisation: every diagnosis carries `first_checks` + `next_steps` actionable output.
- Decision reason codes: `healthy / uncertain / confirmed` decisions include machine-readable reason arrays.
- Clean-import pipeline with provenance proof, SHA256 dedup, and benchmark-ready output.

### Changed
- Rule Engine v2: all target label families now have explicitly tested threshold rules.
- Hybrid fusion retuned: rule confidence boosted for high-evidence cases; ML posterior weighted for multi-label resolution.

---

## [0.1.0] — 2026-02-14 — Rule-Only Prototype

### Added
- Initial project scaffold (`src/parser`, `src/features`, `src/diagnosis`, `src/cli`).
- `pymavlink`-based `.BIN` log parser.
- 37 base telemetry feature extractors (vibration, compass, power, GPS, motors, EKF, control).
- Rule-based diagnosis engine with `vibration_high` and `compass_interference` coverage.
- CLI entry point: `python -m src.cli.main analyze <file.BIN>`.
- Benchmark runner with JSON + markdown output.
- First 10-log pilot benchmark: Macro F1 = 0.20 (vibration F1=0.61, compass F1=0.76).
- `pytest` suite with parser + features + diagnosis contracts.
- GitHub Codespaces dev container.
