# AGENTS.md - Diagnostics-First Execution Playbook

This file is the default operating manual for any AI agent working in this repository.

If you open this project, do not guess what to do next. Follow this file in order.

## Mission Lock

Build an AI-powered ArduPilot `.BIN` **diagnostic analyzer** that identifies the **exact likely root cause**, explains the evidence, and recommends next actions that reduce maintainer/developer triage stress.

## Scope Lock

- In scope: parsing, feature extraction, diagnosis, confidence calibration, abstention/uncertainty handling, causal reasoning, recommendations, benchmarking, reproducibility.
- Out of scope (until all core goals are complete): generic chatbot features, unrelated automation, non-diagnostic product ideas.

## First 10 Minutes (Mandatory Every Session)

1. Read these files first:
   - `README.md`
   - `docs/DEEP_PROGRAM_UNDERSTANDING.md`
   - `AGENTS.md` (this file)
2. Run baseline checks:
   - `pytest -q`
   - `python3 -m src.cli.main --help`
3. Update the "Current Baseline Snapshot" section below.
4. Pick the first unchecked goal in `P0` and work only that scope.
5. End session by updating checkboxes and Session Log.

## Current Baseline Snapshot (Update Every Session)

- Date: 2026-02-28
- `pytest -q`: 56 passed
- Parse success (%): 100%
- Root-cause Top-1 (unseen): 1.00 (Local Benchmark)
- Macro F1: 1.00 (Local Benchmark)
- False critical rate: TBD
- ECE: TBD
- Triage-time reduction: TBD

Known blockers to verify first:

- [x] `RuleEngine.diagnose()` references `_check_events`, and runtime path is stable.
- [x] Feature schema parity across `FeaturePipeline`, `src.constants.FEATURE_NAMES`, and model schemas.
- [x] Parser message retention aligns with extractor requirements (`IMU`, `POWR`, etc.).
- [x] Threshold key alignment between code and `models/rule_thresholds.yaml`.
- [x] ML artifact/schema parity for current feature and label space.

## Task Selection Rule (No Ambiguity)

- If any `P0` item is unchecked -> do the first unchecked `P0` item.
- Else if all `P0` done and any `P1` unchecked -> do first unchecked `P1` item.
- Then `P2`, `P3`, `P4`, then stretch goals.
- Never skip hard gates.

---

## Goal Board (Cross Off)

## P0 - Reliability + Contract Integrity

- [x] `P0-01` Eliminate runtime diagnosis crashes (`analyze`, `features`, `benchmark`).
  - Done when: zero runtime exceptions on valid and malformed input paths.
- [x] `P0-02` Repair parser-feature dependency mismatches.
  - Done when: required message families are retained and consumed by extractors.
- [x] `P0-03` Remove schema drift.
  - Done when: canonical feature list is consistent across constants, pipeline, and model artifacts.
- [x] `P0-04` Align threshold config keys.
  - Done when: threshold overrides are test-verified as active.
- [x] `P0-05` Enforce contracts in tests.
  - Done when: parser/features/diagnosis/benchmark contract failures are CI-blocking.

## P1 - Explainable Diagnostics

- [x] `P1-01` Rule Engine v2 label coverage.
  - Done when: all target labels have explicit tested rules.
- [x] `P1-02` Evidence schema standardization.
  - Done when: every diagnosis has exact feature/value/threshold/context evidence.
- [x] `P1-03` Recommendation schema standardization.
  - Done when: every diagnosis has actionable first checks + next steps.
- [x] `P1-04` Decision reason codes.
  - Done when: `healthy/uncertain/confirmed` decisions include machine-readable reasons.

## P2 - Hybrid Quality + Calibration

- [x] `P2-01` Restore ML artifact integrity.
  - Done when: model/scaler/features/labels are versioned and consistent.
- [x] `P2-02` Tune hybrid fusion.
  - Done when: hybrid outperforms rule-only on locked unseen root-cause Top-1.
- [x] `P2-03` Calibrate confidence + abstain behavior.
  - Done when: ECE target met and low-confidence cases abstain safely.

## P3 - Causal Exact-Problem Diagnosis

- [x] `P3-01` Causal timeline extraction.
  - Done when: first-symptom timing is reliable per subsystem.
- [x] `P3-02` Root-cause arbitration + cascade suppression.
  - Done when: symptom leakage declines with measurable root-cause gain.
- [x] `P3-03` Subsystem blame scoring.
  - Done when: outputs include ranked subsystem likelihoods.

## P4 - Maintainer Stress Reduction

- [x] `P4-01` Fast triage output.
  - Done when: output includes top problem + top 3 checks + ranked fixes.
- [ ] `P4-02` Pilot before/after triage study.
  - Done when: measured median triage-time reduction is documented.
- [ ] `P4-03` False-critical audit and mitigation.
  - Done when: false-critical metric target is met.

---

## Hard Gates (Cannot Be Skipped)

- [ ] Gate A: 0 diagnosis runtime crashes on benchmark runs.
- [ ] Gate B: 100% predictions include evidence + recommendation.
- [ ] Gate C: No fabricated labels and no train/holdout leakage.
- [ ] Gate D: Reproducible benchmark from clean environment.
- [ ] Gate E: Calibration and abstention report included.

## Final Success Targets

- [ ] Root-cause Top-1 on locked unseen set: `>= 50-60%`.
- [ ] ECE: `<= 0.08`.
- [ ] False critical rate: `<= 10%`.
- [ ] Median triage-time reduction: `>= 40%`.
- [ ] Parse reliability: `>= 99%`.

---

## Perfect — then let's shape your proposal as a diagnostics-first GSoC plan

_(not generic AI, not chatbot)_

This is a timeline that can genuinely set a new bar in flight-log diagnostics.

## GSoC Timeline (Diagnostics-Only, 12 Coding Weeks + Bonding)

| Phase | Weeks | Milestone | Deliverables | Hard Gate |
|---|---|---|---|---|
| Community Bonding | CB-1 to CB-3 | Diagnostic scope lock | Taxonomy v1 (labels, severity, root-cause vs symptom policy), benchmark protocol, weekly mentor plan | No ambiguous labels; benchmark split frozen |
| Coding Phase 1 | W1-W2 | Reliability foundation | Fix runtime blockers, parser-feature contract tests, schema consistency checks | 0 diagnosis crashes, parse success >= 99%, core tests green |
| Coding Phase 1 | W3-W4 | Explainable Rule Engine v2 | Evidence-rich diagnosis output (what fired + why + recommendation), threshold config unification | 100% predictions include evidence + recommendation |
| Coding Phase 1 | W5-W6 | Midterm: Hybrid v1 + calibration | Reproducible training pipeline, ML artifact loading, calibrated confidence + abstain logic | Midterm demo: stable CLI + reproducible benchmark run |
| Midterm Evaluation | End W6 | Formal checkpoint | Report + demo + metrics sheet + risk updates | Mentor sign-off on reliability + explainability |
| Coding Phase 2 | W7-W8 | Causal timeline engine | First-symptom detection, cascade suppression, root-cause arbitration | Root-cause precision improves vs pre-causal baseline |
| Coding Phase 2 | W9-W10 | Actionable diagnostics | "Top problem + top 3 checks + ranked fixes" output format | Maintainer review says outputs are operationally useful |
| Coding Phase 2 | W11 | Stress-reduction validation | Timed triage experiment (before vs after), false-critical audit | >=40% triage-time reduction in pilot set |
| Coding Phase 2 | W12 | Final release + handoff | Final docs, model card, benchmark report, demo video/notebook | Fully reproducible final run from clean environment |
| Final Evaluation | End W12 | Submission | GSoC final report + merged docs + future roadmap | All promised core goals complete |

## Industry-Breaking Standards You Should Explicitly Promise

- Causal diagnosis, not just anomaly flags: identify **root cause first**, not symptom spam.
- Confidence honesty: calibrated probabilities + mandatory abstain/human-review state.
- Evidence traceability: every diagnosis tied to exact features/events/timestamps.
- Provenance-safe benchmarks: no fabricated labels, no leakage, reproducible splits.
- Maintainer KPI focus: success measured by triage-time reduction, not only F1.
- Reproducible science: one-command benchmark reproduction and documented model behavior.

## Target Metrics (Ambitious but realistic for GSoC)

- Reliability: 0 runtime exceptions on benchmark runs.
- Diagnostic quality: root-cause Top-1 from current baseline (~21%) to >=50-60% on locked unseen set.
- Trust: Expected Calibration Error <= 0.08 by final.
- Safety: false critical alerts <= 10%.
- Workflow impact: median triage time reduced by >=40%.

## Weekly Operating Rhythm (Important for mentor confidence)

- 2 mentor syncs/week (design + results review).
- 1 public weekly report (done, blocked, next).
- Every Friday: benchmark snapshot + regression check.
- Every 2 weeks: milestone demo against hard gate.
- Scope freeze rule: diagnostics core always prioritized over stretch features.

## Stretch Goals (Only if core milestones are complete)

- [ ] Similar-case retrieval from historical logs for faster maintainer context.
- [ ] Batch triage mode with duplicate incident clustering.
- [ ] Firmware regression sentinel for rising failure patterns.

## Ready-to-Paste GSoC Proposal Checklist

- [ ] Problem statement (diagnostics-first motivation and maintainer pain reduction).
- [ ] Detailed timeline by week (table above).
- [ ] Deliverables + evaluation criteria (hard gates and metrics).
- [ ] Risk mitigation + fallback plan.
- [ ] Final impact statement for ArduPilot maintainers.

---

## Session Log Template (Fill Every Work Session)

- Date:
- Goal ID worked:
- Changes made:
- Tests run + status:
- Metrics delta (`Top1`, `MacroF1`, `FalseCritical`, `ECE`):
- Blockers:
- Next task:
