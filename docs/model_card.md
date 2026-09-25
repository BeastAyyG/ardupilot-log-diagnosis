# ArduPilot Log Diagnosis — Model Card

## Current status

This is a diagnostic aid for offline ArduPilot DataFlash logs. It combines
deterministic rules, a tabular ML classifier, and an Isolation Forest anomaly
detector. It is **not approved for autonomous flight decisions or unsupervised
maintenance decisions**.

The dashboard's default model is a legacy RandomForest artifact with a
94-feature compatibility schema and nine trained labels. The runtime extracts
111 finite features. No candidate has passed the release gates, and none is promoted.

## Release evidence (real-log benchmark v1, 2026-09-25)

The benchmark covers 41 real logs from 37 incidents. Models are trained and
tested out-of-fold with every incident grouped: 5 folds × 5 seeds. Labels are
provisional ([CORRECTIONS.md, C11](../CORRECTIONS.md#c11)). Source:
`data/benchmark/results/paper_eval_v1.json`, commit `38d342e`, reproduced by
`python training/paper_eval.py`.

| Gate | Result | Required | Status |
| --- | ---: | ---: | --- |
| Incident-grouped log macro F1 (RandomForest) | 0.092 ± 0.007 | >= 0.700 | Fail |
| Incident-grouped log macro F1 (ExtraTrees) | 0.078 ± 0.007 | >= 0.700 | Fail |
| Chance baseline (frequency-random) | 0.096 (95th percentile 0.175) | — | reference |
| Incident-level ECE (RandomForest) | 0.082 | <= 0.080 | Fail |
| Real incidents available | 37 | >= 50 | Fail |
| Runtime feature schema | 111 | exact match | Pass |

On current data the tree models do not beat chance, and the rule engine
alone (0.159) stays within the chance range. The same RandomForest scores
0.890 when windows are split at random. That gap is the leakage effect that
inflated earlier reports.

**Historical figures, not reproducible (see `docs/EVIDENCE_LEDGER.md`):**
- `v3_unambiguous`: 0.500 / ECE 0.153. Its pool must have included
  simulated BASiC flights, and F1 was scored over all classes.
- `v3_grouped`: 0.559 / 0.158. Rejected because of contradictory labels,
  most of them created by rule-engine relabelling (C8/C9).
- `v2_111`: 0.670. Filename-only grouping allowed incident leakage.
- ExtraTrees exploratory run: 0.584–0.596.

All of these are superseded, and no artifact is promoted.

## Label coverage

The trained ML artifact currently covers nine labels. `brownout`,
`crash_unknown`, `mechanical_failure`, `setup_error`, and `thrust_loss` are
rules-only until there are enough independently sourced, expert-labelled logs
to train and evaluate them.

## What the system does

- Extracts 111 telemetry features from supported offline logs, replacing
  missing or non-finite measurements safely.
- Runs deterministic failure rules with evidence and recommendations.
- Scores a trained ML model where its artifact schema matches the runtime.
- Flags out-of-distribution telemetry using an Isolation Forest whose feature
  schema is checked before scoring.
- Produces reports, plots, exports, and review-oriented analysis tools.

## Important limitations

- A label returned by the hybrid engine is a triage hypothesis, not a verified
  root cause.
- Live MAVLink mode uses rules only; it does not use the offline ML or anomaly
  model.
- PX4 ULog, MAVLink TLog, and Betaflight adapters are generic/optional and are
  not validated as equivalent to ArduPilot diagnosis.
- Review-only and experimental tools never change vehicle parameters.
- Low-quality, partial, or corrupted logs can reduce coverage; inspect the
  quality report alongside every diagnosis.

## Data and evaluation requirements

Every training log must retain provenance, a reviewable label source, and a
group identifier so that windows from the same flight cannot cross the holdout
split. Forum-search labels are provisional and are never automatically merged
into training data.
