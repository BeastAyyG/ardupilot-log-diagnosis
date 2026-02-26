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
4. Work only the first unchecked `P0` item.
5. End by updating checkboxes and Session Log in `AGENTS.md`.

## Current Priority Queue (Strict)

Complete in this order. Do not skip.

### P0 - Reliability + Contract Integrity

- [ ] `P0-01` Eliminate runtime diagnosis crashes.
- [ ] `P0-02` Repair parser-feature dependency mismatches.
- [ ] `P0-03` Remove schema drift.
- [ ] `P0-04` Align threshold config keys.
- [ ] `P0-05` Enforce contracts in tests.

### P1 - Explainable Diagnostics

- [ ] `P1-01` Rule Engine v2 label coverage.
- [ ] `P1-02` Evidence schema standardization.
- [ ] `P1-03` Recommendation schema standardization.
- [ ] `P1-04` Decision reason codes.

### P2 - Hybrid Quality + Calibration

- [ ] `P2-01` Restore ML artifact integrity.
- [ ] `P2-02` Tune hybrid fusion.
- [ ] `P2-03` Calibrate confidence + abstain behavior.

### P3 - Causal Exact-Problem Diagnosis

- [ ] `P3-01` Causal timeline extraction.
- [ ] `P3-02` Root-cause arbitration + cascade suppression.
- [ ] `P3-03` Subsystem blame scoring.

### P4 - Maintainer Stress Reduction

- [ ] `P4-01` Fast triage output.
- [ ] `P4-02` Pilot before/after triage study.
- [ ] `P4-03` False-critical audit and mitigation.

## Immediate Blockers Checklist

Verify these before starting deeper work:

- [ ] `RuleEngine.diagnose()` runtime path is stable (`_check_events` reference resolved).
- [ ] Feature schema parity across pipeline, constants, and model schema files.
- [ ] Parser retains message families required by extractors (`IMU`, `POWR`, etc.).
- [ ] Threshold keys are aligned with `models/rule_thresholds.yaml`.
- [ ] ML artifacts and label/feature schemas match current taxonomy.

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
