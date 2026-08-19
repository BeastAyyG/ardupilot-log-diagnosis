# ArduPilot Log Diagnosis — Model Card

## Current status

This is a diagnostic aid for offline ArduPilot DataFlash logs. It combines
deterministic rules, a tabular ML classifier, and an Isolation Forest anomaly
detector. It is **not approved for autonomous flight decisions or unsupervised
maintenance decisions**.

The dashboard's default model is a legacy RandomForest artifact with a
94-feature compatibility schema and nine trained labels. The runtime extracts
111 finite features. The safe `v3_unambiguous` candidate has not passed the
release gates and is not promoted; `v3_grouped` is rejected because two source
URL groups contain contradictory labels.

## Release evidence (honest candidate `v3_unambiguous`, 2026-08-05)

| Gate | Result | Required | Status |
| --- | ---: | ---: | --- |
| Grouped log-level macro F1 | 0.500 | >= 0.700 | Fail |
| Independent holdout source incidents | 23 | >= 50 | Fail |
| Incident-level expected calibration error | 0.153 | <= 0.080 | Fail |
| Runtime feature schema | 111 | exact match | Pass |

Because the release gates fail, the candidate remains quarantined. The
earlier `v2_111` score of 0.670 is not comparable: it used filename-only
grouping and a column-order primary-label fallback that allowed incident
cross-split leakage. The intermediate `v3_grouped` run scored F1 0.559/ECE
0.158 but is invalid because two source URL groups contain contradictory
labels; those four files are excluded from `v3_unambiguous`. See
[production readiness](PRODUCTION_READINESS.md) for the
complete promotion checklist.

Exploratory ExtraTrees retraining reached 0.596 Macro F1 on the fixed grouped
holdout, but incident ECE was 0.170 (five-split mean F1 0.584 and ECE 0.167).
Temperature scaling remained above the 0.08 calibration gate, so no exploratory
artifact is promoted.

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
