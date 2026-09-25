# The Definitive ML Strategy Blueprint

## The Core Insight You've Identified

> If a failure is deterministic and mathematically repeatable, rule-based systems
> will almost always beat Machine Learning.

This is exactly right. Your rule engine works because drone physics are deterministic.
A motor producing 1950 PWM while the craft is losing altitude IS thrust loss — no
statistical correlation needed. ML cannot improve on a mathematical certainty.

**The question is: where does ML actually add value?**

The answer is in the space between "obviously broken" and "subtly degrading" — the
gray zone where no single feature crosses a hard threshold, but the *combination*
of 15 slightly-off features collectively indicates a problem. This is where human
experts use intuition built from thousands of logs, and where ML can learn that
same intuition from data.

---

## The Three-Tier Architecture

Your current architecture is: `Rule Engine → ML Classifier → Hybrid Fusion`

The new architecture should be:

```
Tier 1: PHYSICS RULE ENGINE (deterministic, high-confidence)
  │     Already works. Catches known failures with hard thresholds.
  │     Fires on vibration, compass, EKF, thrust loss, etc.
  │     When it fires with conf > 0.65 → DONE. No ML needed.
  │
  ▼ (Rule engine returns "healthy" or low confidence)
  │
Tier 2: ANOMALY DETECTOR (unsupervised, trained on healthy flights)
  │     Autoencoder learns what "normal" looks like.
  │     High reconstruction error → "Something is wrong, but I don't know what."
  │     Flags for human review with anomaly score.
  │
  ▼ (Anomaly detected, need classification)
  │
Tier 3: PHYSICS-INFORMED CLASSIFIER (supervised, SITL-trained)
        XGBoost trained on SITL-generated + augmented failure features.
        Only runs AFTER anomaly detection flags something.
        Classifies the specific failure type.
```

### Why This Architecture Wins

1. **Tier 1** handles 70-80% of cases deterministically. No data needed.
2. **Tier 2** needs ZERO failure data to train. You only need healthy flights,
   which are 99% of all ArduPilot logs ever created.
3. **Tier 3** gets its data from SITL simulation — you can generate 10,000
   labeled failure logs in one night.

---

## Tier 2: Anomaly Detection (The Game Changer)

### What It Is

An **Autoencoder** is a neural network that compresses your 89 features down to
~10 latent dimensions, then reconstructs them back to 89. It is trained
exclusively on healthy flight data. When you feed it a broken flight, it cannot
reconstruct the features accurately — the reconstruction error is high.

### Why This Solves Your Data Problem

You currently have 52 labeled samples. But you have access to thousands of
healthy flight logs (every ArduPilot user's normal flight is healthy data).
You don't need to label anything. You just need to collect healthy `.BIN` files.

### Implementation (Maps to Your Existing Code)

**New file: `src/diagnosis/anomaly_detector.py`**

```python
import numpy as np

class AnomalyDetector:
    """Autoencoder-based anomaly detection trained on healthy flights.

    The detector learns the distribution of normal flight telemetry.
    When a new log's features deviate significantly from the learned
    normal distribution, it flags an anomaly.

    This approach requires ZERO failure data — only healthy flights.
    """

    def __init__(self, model_path="models/anomaly_detector.joblib"):
        self.model_path = model_path
        self.available = False
        self._load()

    def _load(self):
        try:
            import joblib
            bundle = joblib.load(self.model_path)
            self.encoder = bundle["encoder"]
            self.decoder = bundle["decoder"]
            self.scaler = bundle["scaler"]
            self.threshold = bundle["threshold"]  # 95th percentile of training errors
            self.available = True
        except Exception:
            self.available = False

    def score(self, features: dict, feature_columns: list) -> dict:
        """Compute anomaly score for a feature vector.

        Returns:
            {
                "anomaly_score": float,     # 0.0 = perfectly normal
                "is_anomaly": bool,         # True if score > threshold
                "top_deviations": list,     # which features deviated most
            }
        """
        if not self.available:
            return {"anomaly_score": 0.0, "is_anomaly": False, "top_deviations": []}

        vector = np.array([float(features.get(f, 0.0)) for f in feature_columns])
        X = self.scaler.transform(vector.reshape(1, -1))

        # Encode → Decode → measure reconstruction error
        encoded = self.encoder.predict(X)
        reconstructed = self.decoder.predict(encoded)
        errors = np.abs(X[0] - reconstructed[0])

        anomaly_score = float(np.mean(errors))
        is_anomaly = anomaly_score > self.threshold

        # Find which features contributed most to the anomaly
        top_indices = np.argsort(errors)[-5:][::-1]
        top_deviations = [
            {"feature": feature_columns[i], "error": float(errors[i])}
            for i in top_indices
        ]

        return {
            "anomaly_score": anomaly_score,
            "is_anomaly": is_anomaly,
            "top_deviations": top_deviations,
        }
```

### Alternative: Isolation Forest (Simpler, No Neural Network)

If you want to avoid TensorFlow/PyTorch dependency, use `IsolationForest` from
scikit-learn. It achieves 80-90% of the autoencoder's performance with zero
deep learning complexity:

```python
from sklearn.ensemble import IsolationForest

# Training (on healthy flights only):
iso_forest = IsolationForest(
    n_estimators=200,
    contamination=0.05,  # assume 5% of "healthy" data might actually be bad
    random_state=42,
)
iso_forest.fit(X_healthy)

# Prediction:
score = iso_forest.decision_function(X_new)  # negative = anomaly
is_anomaly = iso_forest.predict(X_new) == -1
```

### Where This Fits in Your Pipeline

In `src/diagnosis/hybrid_engine.py`, after the rule engine runs:

```python
def diagnose(self, features):
    # Tier 1: Rule engine
    rule_results = self.rule_engine.diagnose(features)

    if rule_results and rule_results[0]["confidence"] >= 0.65:
        return rule_results  # High-confidence rule hit — done

    # Tier 2: Anomaly detection
    anomaly = self.anomaly_detector.score(features, self.feature_columns)

    if not anomaly["is_anomaly"]:
        return rule_results or []  # Normal flight, nothing to see

    # Tier 3: ML classification (only if anomaly detected)
    ml_results = self.ml_classifier.predict(features)
    return self._merge(rule_results, ml_results, anomaly)
```

---

## Tier 3: SITL Data Factory (Solving the 52-Sample Problem)

### The Concept

You already have `training/generate_sitl_data.py` with SITL failure configs.
But it only prints MAVProxy commands — it doesn't actually automate anything.

The goal: **a fully automated script that launches SITL, flies a mission,
injects a failure, saves the log, and labels it — 1,000 times overnight.**

### SITL Automation Script

**New file: `training/sitl_data_factory.py`**

```python
"""
Automated SITL failure data generator.

Launches ArduPilot SITL, flies a standard mission, injects a failure
at a random time, saves the .BIN log, and labels it automatically.

Requirements:
    - ArduPilot SITL installed (sim_vehicle.py on PATH)
    - pymavlink installed

Usage:
    python training/sitl_data_factory.py \
        --runs-per-failure 50 \
        --output-dir data/sitl_generated/
"""

import subprocess
import time
import random
import json
import os
import shutil
from pathlib import Path

FAILURE_CONFIGS = {
    "vibration_high": {
        "params": {"SIM_VIB_MOT_MAX": [5, 10, 20, 40]},  # randomize severity
        "inject_after_sec": (15, 45),  # inject between 15-45 seconds
        "label": "vibration_high",
    },
    "motor_failure_partial": {
        "params": {"SIM_ENGINE_FAIL": [1], "SIM_ENGINE_MUL": [0.3, 0.5, 0.7]},
        "inject_after_sec": (20, 50),
        "label": "motor_imbalance",
    },
    "motor_failure_total": {
        "params": {"SIM_ENGINE_FAIL": [1], "SIM_ENGINE_MUL": [0.0]},
        "inject_after_sec": (20, 40),
        "label": "mechanical_failure",
    },
    "gps_loss": {
        "params": {"SIM_GPS_DISABLE": [1]},
        "inject_after_sec": (30, 60),
        "label": "gps_quality_poor",
    },
    "gps_glitch": {
        "params": {"SIM_GPS_GLITCH_X": [50, 100, 200],
                   "SIM_GPS_GLITCH_Y": [50, 100, 200]},
        "inject_after_sec": (20, 50),
        "label": "gps_quality_poor",
    },
    "compass_interference": {
        "params": {"SIM_MAG_MOT": [30, 50, 80]},
        "inject_after_sec": (15, 45),
        "label": "compass_interference",
    },
    "rc_failsafe": {
        "params": {"SIM_RC_FAIL": [1]},
        "inject_after_sec": (30, 50),
        "label": "rc_failsafe",
    },
    "battery_sag": {
        # Simulate battery with high internal resistance
        "params": {"SIM_BATT_VOLTAGE": [10.5, 11.0, 11.5]},
        "inject_after_sec": (20, 40),
        "label": "power_instability",
    },
    "healthy": {
        "params": {},
        "inject_after_sec": None,
        "label": "healthy",
    },
}

# Each run:
# 1. Start SITL with default params
# 2. Arm and takeoff to 20m in GUIDED mode
# 3. Fly for inject_after_sec seconds
# 4. Inject failure params via MAVProxy
# 5. Continue for 30 more seconds (or until crash)
# 6. Copy the .BIN log to output directory
# 7. Write ground_truth label
```

### Randomization Is Critical

The key insight from your analysis: **if you train ML on a 5-inch quad and test
on a 10-inch hex, it fails.** SITL solves this because you can randomize:

- **Frame type**: `--frame quad`, `--frame hexa`, `--frame octa`
- **Weight**: `SIM_WEIGHT_KG` parameter
- **Wind conditions**: `SIM_WIND_SPD`, `SIM_WIND_DIR`
- **Failure severity**: e.g., `SIM_ENGINE_MUL` from 0.0 to 0.9
- **Failure onset time**: random injection point during flight

Each of these variations produces a slightly different failure signature in the
telemetry. The ML model learns the *invariant pattern* across all variations,
not the specific numbers from one airframe.

---

## Data Augmentation (Multiplying Your Existing 52 Logs)

### 1. Window Slicing (52 logs → 6,000+ samples)

Your current approach: one feature vector per entire flight log.

Better approach: **slice each log into 5-second overlapping windows**, extract
features from each window independently. A 5-minute flight becomes 60 samples.

```python
def window_slice(features_timeseries, window_sec=5.0, overlap=0.5):
    """Slice feature timeseries into overlapping windows.

    Args:
        features_timeseries: list of (timestamp, feature_dict) tuples
        window_sec: window duration in seconds
        overlap: fraction of overlap between consecutive windows

    Returns:
        list of aggregated feature dicts, one per window
    """
    step = window_sec * (1 - overlap)
    windows = []
    t_start = features_timeseries[0][0]
    t_end = features_timeseries[-1][0]

    t = t_start
    while t + window_sec <= t_end:
        window_data = [
            f for (ts, f) in features_timeseries
            if t <= ts < t + window_sec
        ]
        if window_data:
            windows.append(aggregate_window(window_data))
        t += step

    return windows
```

**Implementation note:** This requires changing your extractors to work on
message subsets rather than the full log. You would add a `time_range` filter
to `BaseExtractor._safe_stats()`.

### 2. Jittering (Adding Noise)

Add small Gaussian noise to your existing feature vectors:

```python
def jitter_features(features: dict, noise_scale=0.02) -> dict:
    """Add Gaussian noise to all numeric features.

    noise_scale=0.02 means ±2% variation — enough to prevent memorization
    but small enough to preserve the failure signature.
    """
    augmented = {}
    for key, val in features.items():
        if isinstance(val, (int, float)) and not key.startswith("_"):
            noise = np.random.normal(0, abs(val) * noise_scale)
            augmented[key] = val + noise
        else:
            augmented[key] = val
    return augmented
```

### 3. Scaling (Simulating Different Airframes)

A 5-inch quad with vibration issues produces `vibe_z_max = 45 m/s²`.
A 10-inch hex with the SAME vibration issue might produce `vibe_z_max = 32 m/s²`
because the larger frame dampens vibration differently.

```python
def scale_features(features: dict, scale_groups: dict) -> dict:
    """Scale feature groups to simulate different airframes.

    scale_groups = {
        "vibe_": (0.6, 1.4),      # ±40% variation in vibration amplitude
        "motor_spread": (0.7, 1.3), # ±30% variation in motor output
        "bat_curr": (0.8, 1.2),    # ±20% variation in current draw
    }
    """
    augmented = dict(features)
    for prefix, (lo, hi) in scale_groups.items():
        scale = np.random.uniform(lo, hi)
        for key in augmented:
            if key.startswith(prefix) and isinstance(augmented[key], (int, float)):
                augmented[key] *= scale
    return augmented
```

### 4. Synthetic Injection (The Most Powerful Technique)

Take a verified healthy log and **mathematically inject a failure signature**:

```python
def inject_voltage_sag(features: dict) -> dict:
    """Inject a synthetic voltage sag into a healthy flight's features.

    A real voltage sag looks like:
    - bat_volt_min drops from 14.8V to 10.5V
    - bat_volt_range increases from 0.3V to 4.3V
    - bat_sag_ratio jumps from 0.02 to 0.29
    - bat_curr_max spikes (high current draw causes the sag)
    """
    sag = dict(features)
    sag_depth = np.random.uniform(2.0, 5.0)  # volts dropped
    sag["bat_volt_min"] = max(sag["bat_volt_min"] - sag_depth, 9.0)
    sag["bat_volt_range"] = sag["bat_volt_max"] - sag["bat_volt_min"]
    sag["bat_sag_ratio"] = sag["bat_volt_range"] / sag["bat_volt_max"] if sag["bat_volt_max"] > 0 else 0
    sag["bat_curr_max"] *= np.random.uniform(1.5, 3.0)
    return sag
```

---

## Physics-Informed Features (What to Actually Feed the ML)

Your current ML model receives 89 raw features. Many of these are redundant
or noisy. The key insight: **feed ML the same ratios and relationships that
your rule engine checks.**

### New Derived Features to Add

| Feature | Formula | Why It Matters |
|---|---|---|
| `thrust_weight_ratio` | `motor_output_mean / motor_hover_ratio` | <1.0 = underpowered |
| `voltage_internal_resistance` | `bat_volt_range / bat_curr_max` | High = bad battery |
| `attitude_tracking_error` | `att_desroll_err / att_roll_std` | Ratio of command error to noise |
| `ekf_health_composite` | `ekf_vel_var_max + ekf_pos_var_max + ekf_hgt_var_max` | Single "EKF badness" score |
| `motor_symmetry_index` | `motor_spread_std / motor_output_mean` | Normalized imbalance |
| `vibe_to_clip_ratio` | `vibe_z_max / (vibe_clip_total + 1)` | How much vibe before clipping |
| `gps_reliability_score` | `gps_fix_pct * gps_nsats_min / gps_hdop_mean` | Single GPS health metric |

These derived features encode the **physics relationships** that your rule
engine already knows. By feeding these to ML instead of (or alongside) the
raw features, you reduce the feature space and give the model a head start.

---

## Updated GSoC Timeline (Incorporating This Strategy)

| Phase | Weeks | What You Build |
|---|---|---|
| Community Bonding | CB1-3 | SITL automation script, collect 200+ healthy logs from forum |
| Phase 1 W1-2 | W1-2 | Tier 2: Train Isolation Forest on healthy logs |
| Phase 1 W3-4 | W3-4 | SITL factory: generate 500+ labeled failure logs |
| Phase 1 W5-6 | W5-6 | Tier 3: Retrain XGBoost on SITL + augmented data |
| Midterm | W6 | Demo: Rule + Anomaly + Classifier pipeline |
| Phase 2 W7-8 | W7-8 | Window slicing, derived features, retrain |
| Phase 2 W9-10 | W9-10 | Benchmark on real forum logs, tune thresholds |
| Phase 2 W11-12 | W11-12 | Final docs, model card, demo notebook |

---

## What NOT to Do

1. **Do NOT replace your rule engine with ML.** The rules are correct. ML is additive.
2. **Do NOT train on raw IMU data.** Use your existing physics-engineered features.
3. **Do NOT chase Macro F1 on 52 samples.** It is meaningless. Wait for SITL data.
4. **Do NOT use deep learning (LSTM, Transformer).** Your data is tabular features,
   not sequences. XGBoost + Isolation Forest will outperform any neural network
   on this task at this data volume.
5. **Do NOT augment data until you have SITL data.** Augmenting 52 noisy samples
   just creates 5,000 noisy samples. Augment clean SITL data instead.
