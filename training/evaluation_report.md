# ML Evaluation Report

**Selected Model**: XGBoost+Calibration  
**Macro F1 Score**: 0.740  
**Calibration**: isotonic (ECE target ≤ 0.08)  
**Oversampling**: SMOTE (adaptive k_neighbors)  
**Best XGBoost Params**: {'learning_rate': 0.2, 'max_depth': 3, 'min_child_weight': 5, 'n_estimators': 200, 'scale_pos_weight': 1}  

Trained on 152 balanced samples, evaluated on 18 unseen samples.
