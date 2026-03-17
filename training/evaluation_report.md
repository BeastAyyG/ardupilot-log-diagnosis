# ML Evaluation Report

**Selected Model**: XGBoost+Calibration  
**Macro F1 Score**: 1.000  
**Calibration**: isotonic (ECE target ≤ 0.08)  
**Oversampling**: SMOTE (adaptive k_neighbors)  
**Best XGBoost Params**: {'learning_rate': 0.05, 'max_depth': 3, 'min_child_weight': 1, 'n_estimators': 100, 'scale_pos_weight': 1}  

Trained on 192 balanced samples, evaluated on 28 unseen samples.
