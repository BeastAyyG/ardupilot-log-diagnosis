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

- The current long-term master plan now lives in `docs/UPGRADE_ROADMAP.md`.
- If this file and the roadmap ever disagree, the roadmap wins.
- Work the roadmap in order. Do not skip ahead to polish or new features.

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

- [x] Scope stayed within one goal ID.
- [x] Relevant tests were run.
- [x] Baseline snapshot in `AGENTS.md` updated.
- [x] Goal checkbox and Session Log updated in `AGENTS.md`.
- [x] Next task is explicitly written.

## Quick Metrics to Track Each Session

- Root-cause Top-1 (unseen): Initial Rule-Baseline Complete (Data Collection Active)
- Macro F1: 0.357 (Baseline ML - requires community logs)
- False critical rate: 0.0% (3 healthy profiles, target ≤ 10%)
- ECE: Isotonic calibration applied; measure via `python training/measure_ece.py`
- Triage-time reduction: 84% reduction per log

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
