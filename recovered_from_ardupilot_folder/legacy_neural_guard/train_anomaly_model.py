import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest
import joblib
import os

def train_model():
    input_file = "training_dataset.csv"
    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found. Run extract_ai_data.py first.")
        return

    print(f"Loading dataset: {input_file}")
    df = pd.read_csv(input_file)
    
    # Feature Engineering: 
    # The messages are asynchronous. To simplify the prototype, we will:
    # 1. Focus only on RCOU (Motor Output) and VIBE (Vibration) as they are strong indicators.
    # 2. Fill missing values or drop non-numeric rows.
    
    # Filter for relevant types
    features = ['Volt', 'Curr', 'VibeX', 'VibeY', 'VibeZ', 'Roll', 'Pitch', 'Yaw', 'C1', 'C2', 'C3', 'C4']
    
    # Create a simplified feature matrix
    # We group by time intervals to align them, or just use the raw samples and fill NaNs
    # For a quick prototype, let's just forward fill values and then drop any remaining NaNs
    
    # Sort by TimeUS
    df = df.sort_values('TimeUS')
    
    # Fill NAs within each log (though here logs are concatenated)
    # A better way is to interpolate, but ffill is faster for now
    X = df[features].ffill().dropna()
    
    print(f"Training on {len(X)} samples with {len(features)} features...")
    
    # Train Isolation Forest
    # contamination is the expected proportion of outliers (roughly)
    model = IsolationForest(n_estimators=100, contamination=0.1, random_state=42)
    model.fit(X)
    
    # Save model
    model_path = "anomaly_model.joblib"
    joblib.dump(model, model_path)
    print(f"Model saved to: {model_path}")

    # Evaluate on the training set (Self-check)
    preds = model.predict(X) 
    # predators: -1 for outlier, 1 for inlier
    outliers_detected = (preds == -1).sum()
    print(f"Detected {outliers_detected} outliers in training data ({outliers_detected/len(X):.2%})")

if __name__ == "__main__":
    train_model()
