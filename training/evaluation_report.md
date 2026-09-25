# ML Evaluation Report (historical — not comparable)

> **Correction (2026-09-25):** this evaluation pool mixed 70 simulated BASiC
> flights with 44 real logs and grouped windows by filename rather than by
> incident. The 0.723 / 0.0418 figures are therefore not real-log performance.
> See [CORRECTIONS.md#c6](../CORRECTIONS.md#c6).

> **Artifact status (2026-08-04):** This report describes the checked-in legacy
> classifier artifact (94 features and 9 trained labels). The current runtime
> pipeline exposes 111 features; the additional features are rule-engine
> features until a full retraining run is completed. Five labels have no
> positive training examples and therefore remain rules-only.

**Selected Model**: RandomForest
**Log-level Macro F1 Score (max window evidence)**: 0.723
**Window-level Macro F1 Score**: 0.446
**Calibration**: none (ECE measured at 0.0418 on the current evaluation split; target <= 0.08)
**Oversampling**: SMOTE (adaptive k_neighbors)  
**Best XGBoost Params**: {'learning_rate': 0.1, 'max_depth': 5, 'min_child_weight': 1, 'n_estimators': 200, 'scale_pos_weight': 1}

Trained on 32310 balanced samples, evaluated on 3131 samples from 24 unseen source logs.
