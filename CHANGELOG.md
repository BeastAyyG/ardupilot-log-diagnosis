# Changelog

All notable changes to ArduPilot AI Log Diagnosis are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

> **Corrections notice (2026-09-25):** several performance and impact claims in
> the entries below were retracted after an audit. Retracted figures are marked
> inline and explained in [CORRECTIONS.md](CORRECTIONS.md). The current honest
> baseline is the reproducible real-log benchmark in docs/EVIDENCE_LEDGER.md.
> Incident-grouped macro-F1 is 0.08–0.09 against a random-guess baseline of
> 0.10, and release gates fail.

---

## [Unreleased]

### Fixed
- Published [CORRECTIONS.md](CORRECTIONS.md), which retracts inflated metrics
  (C1–C10), and removed the corresponding claims from the README, docs, agent
  skill and dashboard.
- Moved unverifiable studies and stale planning documents to `archive/`.
- Hybrid engine tie-breaking no longer depends on `PYTHONHASHSEED`. The same
  log could previously receive a different top diagnosis in different runs.

### Added
- Real-log benchmark v1 (`data/benchmark/`). It has an incident registry
  built from the sealed cohort manifest, with the rule-engine relabels
  reverted and label evidence graded.
- `training/build_incident_registry.py` and `training/paper_eval.py`: the
  leakage study, a rule-engine and CITA comparison, chance baselines and
  bootstrap CIs.
- `HybridEngine` settings for switching CITA off (`--engine hybrid_no_cita`).

---

## [2.0.0] — 2026-03-16 — BASiC import and dashboard

### Summary
**Retracted metrics: see [CORRECTIONS.md#c1](CORRECTIONS.md#c1).** Integrated the simulated **BASiC (Biomisa Arducopter Sensory Critique) Dataset** (70 SITL flights). The originally reported score on this simulated data is withdrawn. Added an interactive 3D mission-replay dashboard.

### Added
- **BASiC Dataset Integration**: Ingested and normalized the 70 simulated BASiC flights from Zenodo (8195068).
- **Interactive 3D Mission Replay:** Added a 3D Plotly dashboard that renders the flight path and drops causal event markers for physical insight.
- **Autonomous Agent Skill (SKILL.md):** Added an agent skill file allowing external agents (like Claude or Cursor) to natively diagnose `.BIN` files over CLI.
- **AI Integrity Output:** A side-by-side validation report was added to compare the ML model's decisions with the rule engine.
- **Subsystem Radar Blame**: Dynamic radar chart for multi-factor "Blame Ranking."
- **Crash Causality Timeline**: Visual swimlane reconstructing the exact sequence of failure onset.
- **Formal Model Card**: Comprehensive documentation of architecture, feature engineering, and calibration.
- **Mentor Scrutiny Report**: GSoC evaluation report and project impact summary.
- **Isotonic Calibration v2**: ~~reported ECE on simulated data~~ [retracted — CORRECTIONS.md#c1](CORRECTIONS.md#c1). Real-incident ECE is 0.153.

### Changed
- **ML Training Pool**: Added the 70 simulated BASiC flights to the training pool (not real incidents; see [CORRECTIONS.md#c6](CORRECTIONS.md#c6)).
- **Hybrid Performance**: [retracted — CORRECTIONS.md#c1](CORRECTIONS.md#c1).
- **UI Aesthetic**: Added a dark-mode interface.
- **Windows UTF-8 Compliance**: Fixed emoji and encoding issues on Windows platforms.

### Fixed
- **Extraction Fallbacks**: Improved 7-Zip and rarfile fallbacks for large dataset imports.
- **Pandas/Numpy Compliance**: Resolved deprecation warnings in the training pipeline.
- **Web API Stability**: Fixed file-locking and unpacking bugs in the FastAPI server.


---

## [1.0.1] — 2026-03-13 — Release Readiness Pass

### Summary
Release-readiness pass completed. The project now ships with a working setup path,
green full test suite, a valid sample log fixture, a cleaned architecture, and a
final exported benchmark report for the release candidate.

### Added
- `pyproject.toml` and `bootstrap.sh` as the primary setup and execution path.
- Architecture, testing, metrics, ML artifact, output format, reproducibility,
  and release-checklist docs under `docs/`.
- Contract layer in `src/contracts.py` plus schema and alignment tests.
- Split CLI command package under `src/cli/commands/`.
- Split rule modules under `src/diagnosis/rules/`.
- Release benchmark exports: `release_benchmark_results.md` and
  `release_benchmark_results.json`.

### Changed
- Refactored the rule engine and CLI into maintainable modules.
- Standardised benchmark metrics to use `Any-Match Accuracy`, `Top-1 Accuracy`,
  and `Exact-Match Accuracy` consistently.
- Updated README, roadmap, and release docs to match actual repo behavior.
- Upgraded the baseline test count to **162 passing tests**.

### Fixed
- Final benchmark export path now runs successfully.
- `sample.bin` analysis now works on a real parseable fixture.
- Old `RCOU`/`CURR` telemetry compatibility in motor and power extraction.
- ML artifact loading now verifies a manifest and fails safely.

---

## [1.0.0] — 2026-02-28 — Initial release

### Summary
First tagged release of the hybrid rule + XGBoost engine. **The original "production sign-off", "zero-leakage 45-log holdout" and triage-time claims are retracted; see [CORRECTIONS.md#c2](CORRECTIONS.md#c2) and [#c3](CORRECTIONS.md#c3).**

### Added
- **Root-cause arbitration engine** (`src/diagnosis/decision_policy.py`): implements Root-Cause Precedence policy — earliest telemetry anomaly suppresses downstream symptoms.
- **Causal cascade suppression**: `vibration_high` → `ekf_failure` cascades are now correctly attributed to the root cause, not the symptom.
- **SHA256 holdout integrity check** (`validate_leakage.py`): cross-validates all train/holdout file hashes before any benchmark run.
- **Expert label mining pipeline** (`ops/expert_label_pipeline/`): mines ArduPilot discussion forum for Developer/staff diagnosis text with zero manual labeling.
- **Unseen holdout builder** (`training/create_unseen_holdout.py`): constructs rigorously isolated evaluation splits.
- **Progress showcase generator** (`training/generate_progress_showcase.py`): produces mentor-ready benchmark reports with integrity attestation.
- **56 passing tests** covering parser, features, diagnosis, CLI, and integration contracts.
- **Production Acceptance Criteria doc** (`docs/PRODUCTION_ACCEPTANCE_CRITERIA.md`): formalises release gates, labeling policy, and holdout strategy.
- **Maintainer Triage Study** (now in `archive/`): withdrawn as unverifiable, see [CORRECTIONS.md#c3](CORRECTIONS.md#c3).

### Changed
- Benchmark results updated to reflect 45-log holdout run (from 10-log v0.1.0 pilot).
- ~~Hybrid engine now outperforms rule-only baseline by confirmed margin.~~ Retracted: no committed evidence ([CORRECTIONS.md#c2](CORRECTIONS.md#c2)).
- CI workflow (`ci.yml`) extended to run `validate_project_boundaries.py` before pytest.
- Ground-truth metadata schema aligned to Root-Cause Precedence policy — historical "EKF Failure" labels audited and relabeled where vibration data showed prior 80 m/s² peaks. **This relabelling used the rule engine's own output and made later evaluation circular; see [CORRECTIONS.md#c8](CORRECTIONS.md#c8).**

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
