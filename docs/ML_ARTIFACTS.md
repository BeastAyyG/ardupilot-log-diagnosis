# ML Artifacts

The ML layer is optional. If the model artifacts are missing or fail schema validation,
the application falls back to rule-only behavior.

## Required Artifacts

- `models/classifier.joblib`
- `models/scaler.joblib`
- `models/feature_columns.json`
- `models/label_columns.json`
- `models/manifest.json`
- `models/anomaly_detector.joblib` (carries its own scaler — see Scaler Alignment)
- `models/anomaly_feature_columns.json`

## Manifest Fields

- `model_version`
- `feature_schema_hash`
- `label_schema_hash`
- `training_dataset_id`
- `calibration_date`
- `threshold_config_hash`

## Runtime Validation

At load time, `src/diagnosis/ml_classifier.py` validates:

- current runtime `FEATURE_NAMES`
- current runtime `VALID_LABELS`
- current `models/rule_thresholds.yaml`

If the manifest does not match the current runtime, the ML classifier is marked unavailable.

## Scaler Alignment

Two scalers exist and are intentionally **not** unified:

| Scaler | Location | Fitted on | Used by |
| --- | --- | --- | --- |
| Classifier | `models/scaler.joblib` | full training dataset (includes failure flights) | `ml_classifier.py` |
| Anomaly | bundled inside `models/anomaly_detector.joblib` | healthy flights only | `anomaly_detector.py` |

Both are `StandardScaler` over 94 features, so they are dimensionally
interchangeable, but their `mean_`/`scale_` statistics differ. Unifying them
would replace the healthy-only reference distribution with one contaminated by
failure flights — destroying exactly the signal the anomaly detector measures.

**Decision (2026-09-26): keep them separate.** Locked in by
`tests/test_scaler_alignment.py`.

## Label Coverage

`VALID_LABELS` has 14 entries, but the ML classifier can only predict **6**:
`compass_interference`, `ekf_failure`, `gps_quality_poor`, `healthy`,
`rc_failsafe`, `vibration_high`.

The other **8 are rules-only** — no ML path can raise them, so their
confidences come from the rule engine alone and are not calibrated by the ML
layer: `brownout`, `crash_unknown`, `mechanical_failure`, `motor_imbalance`,
`pid_tuning_issue`, `power_instability`, `setup_error`, `thrust_loss`.

All 14 have at least one reachable path, which is the Milestone 3 "done when".
Locked in by `tests/test_label_coverage.py`.

Note: the roadmap's dead-label list names `gps_glitch` and `battery_failsafe`,
which are not in `VALID_LABELS`. They correspond to `gps_quality_poor` and
`power_instability`/`brownout`, all of which have rule coverage.

## Regeneration

```bash
python training/build_dataset.py
python training/train_model.py
```
