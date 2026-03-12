# ML Artifacts

The ML layer is optional. If the model artifacts are missing or fail schema validation,
the application falls back to rule-only behavior.

## Required Artifacts

- `models/classifier.joblib`
- `models/scaler.joblib`
- `models/feature_columns.json`
- `models/label_columns.json`
- `models/manifest.json`

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

## Regeneration

```bash
python training/build_dataset.py
python training/train_model.py
```
