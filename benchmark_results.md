# Benchmark Results

## Overall Metrics
- Total logs: 42
- Successful Extractions: 42
- Failed Extractions: 0
- Exact Match Accuracy: 0.21
- Macro F1 Score: 0.11

## Per-Label Metrics
| Label | N | TP | Precision | F1 |
|---|---|---|---|---|
| vibration_high | 8 | 1 | 0.50 | 0.20 |
| compass_interference | 8 | 3 | 0.25 | 0.30 |
| power_instability | 5 | 0 | 0.00 | 0.00 |
| gps_quality_poor | 1 | 0 | 0.00 | 0.00 |
| motor_imbalance | 7 | 3 | 0.14 | 0.21 |
| ekf_failure | 8 | 2 | 1.00 | 0.40 |
| mechanical_failure | 0 | 0 | 0.00 | 0.00 |
| pid_tuning_issue | 1 | 0 | 0.00 | 0.00 |
| rc_failsafe | 4 | 0 | 0.00 | 0.00 |
| crash_unknown | 0 | 0 | 0.00 | 0.00 |

## Confusion Details
- **66bbaf3919__log_10_MAG_INTERFERENCE_1.bin**: Expected ['compass_interference'] vs. Predicted ['motor_imbalance']
- **c648fe37de__log_01_VIBE_HIGH.bin**: Expected ['vibration_high'] vs. Predicted ['compass_interference']
- **00afa36e54__log_0007_vibration_high.bin**: Expected ['vibration_high'] vs. Predicted ['motor_imbalance']
- **12ee853194__log_0009_compass_interference.bin**: Expected ['compass_interference'] vs. Predicted []
- **16c0fe0044__log_0010_compass_interference.bin**: Expected ['compass_interference'] vs. Predicted ['vibration_high']
- **1820618f38__log_0004_vibration_high.bin**: Expected ['vibration_high'] vs. Predicted ['motor_imbalance']
- **7065a3cd0f__log_0003_vibration_high.bin**: Expected ['vibration_high'] vs. Predicted ['motor_imbalance']
- **a004f350c2__log_0005_vibration_high.bin**: Expected ['vibration_high'] vs. Predicted ['crash_unknown']
- **a7290a8733__log_0006_vibration_high.bin**: Expected ['vibration_high'] vs. Predicted ['motor_imbalance']
- **b9daccd263__log_0012_gps_quality_poor.bin**: Expected ['gps_quality_poor'] vs. Predicted []