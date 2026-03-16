# Benchmark Results

## Metric Definitions
- Any-Match Accuracy: at least one predicted label matches ground truth.
- Top-1 Accuracy: highest-confidence prediction matches ground truth.
- Exact-Match Accuracy: predicted label set exactly matches ground truth.

## Overall Metrics
- Total logs: 45
- Successful Extractions: 44
- Failed Extractions: 1
- Any-Match Accuracy: 0.27
- Top-1 Accuracy: 0.18
- Exact-Match Accuracy: 0.07
- Macro F1 Score: 0.14

## Per-Label Metrics
| Label | N | TP | Precision | F1 |
|---|---|---|---|---|
| vibration_high | 10 | 3 | 0.60 | 0.40 |
| compass_interference | 12 | 3 | 0.25 | 0.25 |
| power_instability | 5 | 0 | 0.00 | 0.00 |
| gps_quality_poor | 1 | 0 | 0.00 | 0.00 |
| motor_imbalance | 7 | 3 | 0.14 | 0.21 |
| ekf_failure | 4 | 3 | 0.25 | 0.38 |
| mechanical_failure | 0 | 0 | 0.00 | 0.00 |
| pid_tuning_issue | 2 | 0 | 0.00 | 0.00 |
| rc_failsafe | 3 | 0 | 0.00 | 0.00 |

## Confusion Details
- **66bbaf3919__log_10_MAG_INTERFERENCE_1.bin**: Expected ['compass_interference'] vs. Predicted ['motor_imbalance', 'mechanical_failure']
- **c648fe37de__log_01_VIBE_HIGH.bin**: Expected ['vibration_high'] vs. Predicted ['power_instability', 'vibration_high']
- **00afa36e54__log_0007_vibration_high.bin**: Expected ['vibration_high'] vs. Predicted []
- **16c0fe0044__log_0010_compass_interference.bin**: Expected ['compass_interference'] vs. Predicted ['ekf_failure', 'vibration_high']
- **1820618f38__log_0004_vibration_high.bin**: Expected ['vibration_high'] vs. Predicted ['rc_failsafe', 'motor_imbalance']
- **7065a3cd0f__log_0003_vibration_high.bin**: Expected ['vibration_high'] vs. Predicted ['motor_imbalance', 'compass_interference']
- **a004f350c2__log_0005_vibration_high.bin**: Expected ['vibration_high'] vs. Predicted ['rc_failsafe', 'compass_interference']
- **a7290a8733__log_0006_vibration_high.bin**: Expected ['vibration_high'] vs. Predicted ['ekf_failure', 'vibration_high']
- **b0db91ee3d__log_0008_compass_interference.bin**: Expected ['compass_interference'] vs. Predicted ['ekf_failure', 'compass_interference']
- **b9daccd263__log_0012_gps_quality_poor.bin**: Expected ['gps_quality_poor'] vs. Predicted []