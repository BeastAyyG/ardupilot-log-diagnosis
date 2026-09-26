# Pre-registration: Benchmark v4 (confirmatory holdout)

**Registered:** 2026-09-26. This file MUST be committed before any v4 result is
computed. The commit timestamp is the evidence. It was written before any v4
label was collected.

**Why a separate document from `PREREGISTRATION.md`:** that file covers v3,
which was a *partially* confirmatory test (22 of its 34 logs were already v2
logs). v4 is the **fully confirmatory** holdout the earlier document called for
under "Future holdout": a new set of incidents, labelled with the same protocol,
scored once with frozen code.

## What is frozen

v4 is scored with **exactly** the code, features and metrics that produced the
v3 results. Nothing below may change after v4 labels exist:

- **Models and hyperparameters:** as fixed in `training/paper_eval.py`. They
  were not tuned on v1, v2 or v3, and must not be tuned on v4.
- **Feature schema:** the 94-model / 111-runtime feature set in
  `models/feature_columns.json` / `src/features/pipeline.py`.
- **Windowing contract:** full-log aggregation, max raw-class probability.
- **Metrics:** log-level macro-F1 over classes present, incident-grouped
  5-fold CV over seeds {1, 7, 21, 42, 99}, 95% incident-cluster bootstrap CI
  (2000 resamples, seed 20260925).
- **Baselines:** majority class, frequency-random (2000 draws), rule engine
  alone, rules + fusion with CITA on/off, RandomForest, ExtraTrees,
  LogisticRegression, and the v4 additions (LogAnalyzer mapping, LLM baseline)
  defined in `training/baselines/`.

## Data

- **Source:** new incidents posted on discuss.ardupilot.org, collected with
  `src/data/expert_label_miner.py` / `training/fetch_adaptation_pool.py`, labelled
  from their threads with `training/build_benchmark_v4.py`, following the v3
  protocol (diagnosing post + verbatim quote + certainty; one label per incident).
- **Base:** the v3 set (`data/benchmark/ground_truth_real_v3.json`) is carried
  forward so the evaluation set is continuous; v4's *new* incidents are the only
  unseen data.
- **Unit of independence:** the incident (source forum thread). Threads already
  in v1/v2/v3 are excluded from the *new* pile.
- **Exclusions (fixed in advance):** simulations, non-failure logs, logs with no
  agreed cause, out-of-taxonomy causes, logs with multiple labels within an
  incident.

## Acceptance gate (the bar a Q1 reviewer named)

v4 is accepted as a confirmatory success only if **all** hold:

1. At least **100 incidents** total (v3 base + new), and at least **5 incidents
   per class that is scored**. Smaller classes are merged or reported as
   "unreliable (n < 5)".
2. Labels are **human-reviewed**, not LLM-only. A random 20% of new labels are
   checked by the maintainer; reported Cohen's kappa must be stated.
3. Onset times exist for the labelled logs and are **maintainer-confirmed** for a
   sample (~30). Onset-ordering accuracy is reported (this is the direct test of
   CITA, H3).
4. A single command regenerates every table/figure from the frozen data and the
   numbers match the manuscript (`docs/EVIDENCE_LEDGER.md`).

## Primary outcome

Log-level macro-F1, incident-grouped, with the 95% bootstrap CI.

## Secondary outcomes

- Top-1 accuracy and coverage.
- Log-level ECE (10 bins).
- Onset-ordering accuracy and abstention/coverage.
- Explicit-label subset metrics.

## Hypotheses (reported as they come out)

- **H1 (leakage):** random-window split > incident-grouped split for every model.
- **H2 (no skill):** no method's incident-grouped macro-F1 exceeds the 95th
  percentile of the frequency-random baseline.
- **H3 (CITA):** CITA does not increase correct top-1 rule diagnoses.
- **H4 (confirmatory):** v4's incident-grouped macro-F1 lands within the v3
  bootstrap CI (0.056–0.069 for the tree models). If it does, v3's "at chance"
  conclusion is reproduced on unseen data. If it does not, that is reported too
  — a confirmatory holdout that disagrees with the exploratory result is a
  finding, not a failure.

## What this document does NOT do

It does not promise a positive result. If v4 is also at chance, the publication
is a benchmark + leakage study + negative result (per `PUBLICATION_PLAN.md`,
Step 5). The point of freezing the protocol first is that the outcome is decided
by data, not by what we hoped to show.
