# NEXT_ACTIONS.md - Daily Diagnostics Execution Card

Use this file every time you open the project.

For full policy and goal definitions, see `AGENTS.md`.

## Start Here (Every Session)

1. Read:
   - `README.md`
   - `docs/DEEP_PROGRAM_UNDERSTANDING.md`
   - `AGENTS.md`
2. Run baseline checks:
   - `pytest -q`
   - `python3 -m src.cli.main --help`
3. Update the "Current Baseline Snapshot" in `AGENTS.md`.
4. Work only the first unchecked item in the priority queue below.
5. End by updating checkboxes and Session Log in `AGENTS.md`.

## Current Priority Queue (Strict)

Complete in this order. Do not skip.

### P0 - Reliability + Contract Integrity

- [x] `P0-01` Eliminate runtime diagnosis crashes.
- [x] `P0-02` Repair parser-feature dependency mismatches.
- [x] `P0-03` Remove schema drift.
- [x] `P0-04` Align threshold config keys.
- [x] `P0-05` Enforce contracts in tests.

### P1 - Explainable Diagnostics

- [x] `P1-01` Rule Engine v2 label coverage.
- [x] `P1-02` Evidence schema standardization.
- [x] `P1-03` Recommendation schema standardization.
- [x] `P1-04` Decision reason codes.

### P2 - Hybrid Quality + Calibration

- [x] `P2-01` Restore ML artifact integrity.
- [x] `P2-02` Tune hybrid fusion.
- [x] `P2-03` Calibrate confidence + abstain behavior.

### P3 - Causal Exact-Problem Diagnosis

- [x] `P3-01` Causal timeline extraction.
- [x] `P3-02` Root-cause arbitration + cascade suppression.
- [x] `P3-03` Subsystem blame scoring.

### P4 - Maintainer Stress Reduction

- [x] `P4-01` Fast triage output.
- [x] `P4-02` Pilot before/after triage study.
- [x] `P4-03` False-critical audit and mitigation.

### Upgrade Roadmap (docs/UPGRADE_ROADMAP.md)

- [x] `U-01` SMOTE + class balancing for rare labels (`training/train_model.py`).
- [x] `U-02` GridSearchCV hyperparameter tuning (`training/train_model.py`).
- [x] `U-03` Confidence calibration — ECE ≤ 0.08 (`training/train_model.py`, `training/measure_ece.py`).
- [x] `U-04` tanomaly feature coverage for all 8 labels (`src/diagnosis/hybrid_engine.py`).
- [x] `U-05` False Critical Rate measurement script (`training/measure_fcr.py`).
- [x] `U-06` Abstention / human-review state (`src/diagnosis/decision_policy.py`).
- [x] `U-07` Retrieval engine activation (`src/retrieval/similarity.py`, `src/cli/main.py`).
- [ ] `U-08` Expand `gps_quality_poor` and `pid_tuning_issue` training data (need more labeled logs).
- [x] `U-09` Batch triage mode (`src/cli/main.py` `batch-analyze` command).
- [x] `U-10` Model card (`docs/model_card.md`).
- [x] `U-11` One-command reproducibility script (`training/reproduce_benchmark.py`).
- [x] `U-12` CI regression benchmark via `--assert-min-f1` flag (`.github/workflows/ci.yml`).

### Stretch Goals

- [x] Similar-case retrieval from historical logs.
- [x] Batch triage mode with duplicate incident clustering.
- [x] Firmware regression sentinel for rising failure patterns.

## Immediate Blockers Checklist

Verify these before starting deeper work:

- [x] `RuleEngine.diagnose()` runtime path is stable (`_check_events` reference resolved).
- [x] Feature schema parity across pipeline, constants, and model schema files.
- [x] Parser retains message families required by extractors (`IMU`, `POWR`, etc.).
- [x] Threshold keys are aligned with `models/rule_thresholds.yaml`.
- [x] ML artifacts and label/feature schemas match current taxonomy.

## Session Done Criteria

Before you stop, confirm all items below:

- [ ] Scope stayed within one goal ID.
- [ ] Relevant tests were run.
- [ ] Baseline snapshot in `AGENTS.md` updated.
- [ ] Goal checkbox and Session Log updated in `AGENTS.md`.
- [ ] Next task is explicitly written.

## Quick Metrics to Track Each Session

- Root-cause Top-1 (unseen):
- Macro F1:
- False critical rate:
- ECE:
- Triage-time reduction:

## One-Line Rule

If any `P0` item is unchecked, do not work on anything outside `P0`.

## Next Priority: Data Expansion (U-08)

The only remaining high-priority item is expanding training data for `gps_quality_poor`
and `pid_tuning_issue`. Current counts: 1 and 2 examples respectively. These labels
cannot be reliably trained or evaluated until ≥ 5 verified examples exist per class.

**Recommended next action**:
1. Run `python3 -m src.cli.main mine-expert-labels` with GPS/PID-focused queries.
2. Review candidates with `python3 -m src.cli.main label`.
3. Run `python3 training/build_dataset.py && python3 training/train_model.py` to retrain.
4. Run `python3 training/reproduce_benchmark.py --from-scratch` to verify improvement.

