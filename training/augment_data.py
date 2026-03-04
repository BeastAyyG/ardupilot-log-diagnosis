import pandas as pd
import numpy as np
import os
import argparse

def add_jitter(df, noise_scale=0.02):
    """Add Gaussian noise to all numerical features."""
    augmented = df.copy()
    for col in augmented.columns:
        if augmented[col].dtype in [np.float64, np.float32, np.int64, np.int32]:
            noise = np.random.normal(0, np.abs(augmented[col]) * noise_scale)
            augmented[col] += noise
    return augmented

def scale_features(df):
    """Scale feature groups to simulate different airframes."""
    augmented = df.copy()

    scale_groups = {
        "vibe_": (0.6, 1.4),
        "motor_spread": (0.7, 1.3),
        "bat_curr": (0.8, 1.2),
        "ekf_": (0.5, 1.5)
    }

    for prefix, (lo, hi) in scale_groups.items():
        scale = np.random.uniform(lo, hi)
        for col in augmented.columns:
            if col.startswith(prefix):
                augmented[col] *= scale

    return augmented

def augment_dataset(features_path: str, labels_path: str, num_augmentations: int = 5):
    """
    Apply jitter and scaling to multiply dataset size.
    Saves augmented versions alongside the original.
    """
    if not os.path.exists(features_path) or not os.path.exists(labels_path):
        print(f"Features or labels file not found at {features_path}, {labels_path}")
        return

    df_features = pd.read_csv(features_path)
    df_labels = pd.read_csv(labels_path)

    print(f"Original dataset shape: {df_features.shape}")

    all_features = [df_features]
    all_labels = [df_labels]

    for i in range(num_augmentations):
        # Apply random jitter
        jittered = add_jitter(df_features, noise_scale=np.random.uniform(0.01, 0.05))

        # Apply random scaling
        scaled = scale_features(jittered)

        all_features.append(scaled)
        all_labels.append(df_labels.copy()) # Labels remain identical

    final_features = pd.concat(all_features, ignore_index=True)
    final_labels = pd.concat(all_labels, ignore_index=True)

    # Save back to CSV
    aug_features_path = features_path.replace(".csv", "_augmented.csv")
    aug_labels_path = labels_path.replace(".csv", "_augmented.csv")

    final_features.to_csv(aug_features_path, index=False)
    final_labels.to_csv(aug_labels_path, index=False)

    print(f"Augmented dataset shape: {final_features.shape}")
    print(f"Saved to {aug_features_path} and {aug_labels_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Augment training data.")
    parser.add_argument("--features", default="training/features.csv", help="Input features CSV")
    parser.add_argument("--labels", default="training/labels.csv", help="Input labels CSV")
    parser.add_argument("--multiplier", type=int, default=5, help="Number of augmentations per sample")
    args = parser.parse_args()

    augment_dataset(args.features, args.labels, args.multiplier)
