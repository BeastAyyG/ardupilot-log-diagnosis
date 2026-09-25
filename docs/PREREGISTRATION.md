# Pre-registered Evaluation Protocol

**Registered:** 2026-09-25. This file was committed before any result on
benchmark v3 was computed; the commit timestamp is the evidence.

**Honest scope:** the v1 and v2 results were already known when this was
written, and 22 of v3's 34 logs are v2 logs. v3 is therefore a
**partially confirmatory** test. Only the 12 newly labelled pool logs are
unseen, and the protocol below was not changed after seeing them. A fully
confirmatory test requires a new holdout (see "Future holdout").

## Data

- **Benchmark v3** (`data/benchmark/ground_truth_real_v3.json`):
  - the v2 thread-verified real logs;
  - plus previously unlabelled real logs from `thread_annotations_pool.json`
    with status `labelled`, exactly one hash-matched `.bin`, and no label
    conflict within their incident.
- **Unit of independence:** the incident, meaning the source forum thread.
- **Exclusions,** fixed in advance: simulations, non-failure logs, logs with
  no agreed cause, out-of-taxonomy causes, and logs with multiple labels.

## Primary outcome

- **Metric:** log-level macro-F1 over the classes present, with
  **incident-grouped** 5-fold cross-validation repeated over seeds
  {1, 7, 21, 42, 99}.
- **Uncertainty:** a 95% incident-cluster bootstrap CI (2000 resamples,
  seed 20260925).

## Secondary outcomes

- Top-1 accuracy and coverage (the share of logs with any diagnosis).
- Log-level ECE (10 bins).
- The same metrics restricted to labels with `certainty = explicit`.

## Methods compared (no tuning on v3)

- **Chance baselines:** majority class, and frequency-random (2000 draws).
- **Rule engine** alone.
- **Rules + fusion,** with CITA on and off.
- **RandomForest, ExtraTrees and LogisticRegression.** Hyperparameters are
  as fixed in `training/paper_eval.py`; they were not tuned on any benchmark
  version.
- **Split-protocol comparison:** random window, grouped by log file, and
  grouped by incident.

## Hypotheses

- **H1 (leakage):** the random-window split scores higher than the
  incident-grouped split for every model.
- **H2 (no skill):** no method's incident-grouped macro-F1 exceeds the
  95th percentile of the frequency-random baseline.
- **H3 (CITA):** CITA does not increase the number of correct top-1 rule
  diagnoses.

A hypothesis is reported as it came out, whichever way that is.

## Future holdout (fully confirmatory)

Incidents posted on discuss.ardupilot.org **after 2026-09-25**:
- will be collected, labelled with the same protocol, and frozen;
- will be scored once with the methods above, without any change to code or
  hyperparameters.
