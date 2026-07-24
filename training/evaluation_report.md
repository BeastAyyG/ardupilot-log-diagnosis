# ML Evaluation Report

**Selected Model**: XGBoost+Calibration
**Macro F1 Score**: 0.603
**RandomForest Baseline Macro F1**: 0.608
**Uncalibrated XGBoost Macro F1**: 0.669
**Calibration**: sigmoid (ECE target ≤ 0.08)
**Oversampling**: SMOTE (adaptive k_neighbors)
**Duplicate Rows Removed**: 0
**Train/Test Flight Groups**: 88/22
**Best XGBoost Params**: {'learning_rate': 0.2, 'max_depth': 4, 'min_child_weight': 1, 'n_estimators': 300, 'scale_pos_weight': 1}

Trained on 192 balanced samples, evaluated on 22 unseen samples.

This report describes the currently deployed pre-merge artifact. The locked-holdout
experimental retrain on the two additional expert-verified motor logs is archived under
`archive/experimental-expert-merge-models-2026-07-24/`; it was not deployed because its
top-label ECE worsened.
