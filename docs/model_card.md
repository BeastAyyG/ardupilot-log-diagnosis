# ArduPilot Log Diagnosis — Model Card

This project combines deterministic ArduPilot rules, a calibrated XGBoost classifier,
an Isolation Forest, and Crash-Immune Temporal Arbitration (CITA). The current artifacts
are development models; they are not cleared for autonomous maintenance or flight-safety
decisions.

## Current evaluation

| Metric | Result | Gate | Status |
|---|---:|---:|---|
| Calibrated macro F1 | 0.603 | ≥ 0.50 | Pass |
| Uncalibrated XGBoost macro F1 | 0.669 | Reference | Measured |
| Top-label ECE | 0.1268 | ≤ 0.08 | **Fail** |
| Group isolation | 88 train / 22 test flights | No shared `flight_id` | Pass |
| Exact duplicate feature rows | 0 | 0 | Pass |

The current feature table contains 114 unique flights. The deployed artifact is still
the pre-promotion 110-eligible snapshot recorded in `models/manifest.json`, with an
88/22 group-isolated train/test split and zero duplicate feature rows. The July 24
review promoted 2 `motor_imbalance` candidates out of a 24-log queue, but the
locked-holdout retrain that included them was archived rather than deployed because its
ECE worsened.

`motor_imbalance` and `power_instability` each have only one holdout flight and scored
zero F1 in this split. Those classes need more manually verified logs before their ML
predictions can be treated as reliable.

## Training and evaluation controls

- Median imputation is fitted on the training fold only.
- Train and test groups are separated by `flight_id`.
- SMOTE is applied only after the grouped split.
- The outer holdout is used for reporting, not model-family selection.
- Small-data probability calibration uses sigmoid calibration.
- ECE is measured only on the saved unseen holdout by default.
- Model loading fails closed when artifact or library versions are incompatible.

The exact environment is recorded in `constraints.txt`; model metadata and holdout IDs
are recorded in `models/manifest.json`.

## Architecture and interpretation

The rule engine produces physics-grounded evidence and recommendations. XGBoost adds a
statistical signal when a supported failure pattern is present. The Isolation Forest
flags out-of-distribution logs, and CITA uses anomaly onset ordering to avoid promoting
post-impact symptoms as the root cause.

Because the calibration gate currently fails, ML probabilities are advisory. A result
marked `uncertain` requires human review, and every diagnosis should be checked against
its raw telemetry evidence.

## Data limitations

The current training distribution is small and imbalanced. Provisional rule-generated
labels are kept review-only and are not treated as verified ground truth until
`human_verified: true` is set. Future gains should come from additional expert-reviewed,
SHA-deduplicated logs—especially power, motor, GPS, and PID failures—not from
duplicating full flights as artificial windows.

Last verified: 2026-07-24.
