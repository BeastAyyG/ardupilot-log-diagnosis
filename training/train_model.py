"""
Train multi-label classifier from feature/label CSVs.
Usage: python training/train_model.py
"""
import os
import json
import numpy as np
import pandas as pd
import joblib
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestClassifier
from sklearn.multiclass import OneVsRestClassifier
from sklearn.metrics import precision_recall_fscore_support
from xgboost import XGBClassifier

def train():
    features_csv = "training/features.csv"
    labels_csv = "training/labels.csv"
    model_dir = "models/"
    
    if not os.path.exists(features_csv) or not os.path.exists(labels_csv):
        print("Dataset CSVs not found. Run build_dataset.py first.")
        return
        
    df_feat = pd.read_csv(features_csv)
    df_lab = pd.read_csv(labels_csv)
    
    valid_labels = df_lab.columns[df_lab.sum() >= 1].tolist()
    if not valid_labels:
        print("Not enough examples to train any labels (require at least 1).")
        return
        
    df_lab = df_lab[valid_labels]
    
    # Up-sample data for stable local testing where there are very few logs
    if len(df_feat) < 10:
        df_feat = pd.concat([df_feat]*5, ignore_index=True)
        df_lab = pd.concat([df_lab]*5, ignore_index=True)
    
    X = df_feat.values
    y = df_lab.values
    
    # Stratified split is tough for multi-label, using random split
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    
    print("Training RandomForest baseline...")
    rf_clf = OneVsRestClassifier(RandomForestClassifier(n_estimators=100, max_depth=10, class_weight='balanced', random_state=42))
    rf_clf.fit(X_train_scaled, y_train)
    
    print("Training XGBoost...")
    xgb_clf = OneVsRestClassifier(XGBClassifier(n_estimators=100, max_depth=6, learning_rate=0.1, random_state=42))
    xgb_clf.fit(X_train_scaled, y_train)
    
    # Evaluate
    def evaluate(model, name):
        y_pred = model.predict(X_test_scaled)
        prec, rec, f1, support = precision_recall_fscore_support(y_test, y_pred, zero_division=0)
        macro_f1 = np.mean(f1)
        print(f"--- {name} Results ---")
        print(f"Macro F1: {macro_f1:.3f}")
        for i, label in enumerate(valid_labels):
            if support[i] > 0:
                print(f" {label:20} -> F1: {f1[i]:.3f} (Support: {support[i]})")
        return macro_f1, model
        
    rf_score, rf_model = evaluate(rf_clf, "RandomForest")
    xgb_score, xgb_model = evaluate(xgb_clf, "XGBoost")
    
    best_model = xgb_model if xgb_score >= rf_score else rf_model
    best_name = "XGBoost" if xgb_score >= rf_score else "RandomForest"
    
    print(f"\nSaving {best_name} as final model...")
    os.makedirs(model_dir, exist_ok=True)
    
    joblib.dump(best_model, os.path.join(model_dir, "classifier.joblib"))
    joblib.dump(scaler, os.path.join(model_dir, "scaler.joblib"))
    
    with open(os.path.join(model_dir, "feature_columns.json"), "w") as f:
        json.dump(df_feat.columns.tolist(), f)
    with open(os.path.join(model_dir, "label_columns.json"), "w") as f:
        json.dump(valid_labels, f)
        
    # Write report
    report_md = f"""# ML Evaluation Report
Selected Model: {best_name}
Macro F1 Score: {max(rf_score, xgb_score):.3f}

Trained on {len(X_train)} samples, evaluated on {len(X_test)} samples.
"""
    with open("training/evaluation_report.md", "w") as f:
        f.write(report_md)
        
    print("Training complete!")

if __name__ == "__main__":
    train()
