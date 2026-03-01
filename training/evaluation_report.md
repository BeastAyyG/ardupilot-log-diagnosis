# ML Evaluation Report

**Selected Model**: XGBoost+Calibration  
**Macro F1 Score**: 0.357  
**Calibration**: isotonic (ECE target ≤ 0.08)  
**Oversampling**: SMOTE (adaptive k_neighbors)  
**Best XGBoost Params**: {'learning_rate': 0.1, 'max_depth': 3, 'min_child_weight': 3, 'n_estimators': 100, 'scale_pos_weight': 1}  

Trained on 56 balanced samples, evaluated on 10 unseen samples.
