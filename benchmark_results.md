# Benchmark Results

## Overall Metrics
- Total logs: 45
- Successful Extractions: 44
- Failed Extractions: 1
- Exact Match Accuracy: 0.39
- Macro F1 Score: 0.24

## Per-Label Metrics
| Label | N | TP | Precision | F1 |
|---|---|---|---|---|
| vibration_high | 9 | 4 | 0.50 | 0.47 |
| compass_interference | 10 | 8 | 0.44 | 0.57 |
| power_instability | 5 | 0 | 0.00 | 0.00 |
| gps_quality_poor | 1 | 0 | 0.00 | 0.00 |
| motor_imbalance | 7 | 1 | 0.17 | 0.15 |
| ekf_failure | 5 | 3 | 0.75 | 0.67 |
| mechanical_failure | 0 | 0 | 0.00 | 0.00 |
| pid_tuning_issue | 2 | 0 | 0.00 | 0.00 |
| rc_failsafe | 5 | 1 | 0.50 | 0.29 |

## Confusion Details
- **c648fe37de__log_01_VIBE_HIGH.bin**: Expected ['vibration_high'] vs. Predicted ['compass_interference']
- **16c0fe0044__log_0010_compass_interference.bin**: Expected ['compass_interference'] vs. Predicted ['ekf_failure']
- **7065a3cd0f__log_0003_vibration_high.bin**: Expected ['vibration_high'] vs. Predicted ['compass_interference']
- **a004f350c2__log_0005_vibration_high.bin**: Expected ['vibration_high'] vs. Predicted ['rc_failsafe']
- **b9daccd263__log_0012_gps_quality_poor.bin**: Expected ['gps_quality_poor'] vs. Predicted []
- **c1bcef192f__log_0002_vibration_high.bin**: Expected ['vibration_high'] vs. Predicted ['compass_interference']
- **4dbb9b5fad__log_0009_pid_tuning_issue.bin**: Expected ['pid_tuning_issue'] vs. Predicted ['mechanical_failure']
- **0818fe7e5c__log_0010_rc_failsafe.bin**: Expected ['rc_failsafe'] vs. Predicted ['gps_quality_poor']
- **af2836cad8__log_0009_rc_failsafe.bin**: Expected ['rc_failsafe'] vs. Predicted ['gps_quality_poor']
- **b89fc87fea__log_0008_rc_failsafe.bin**: Expected ['rc_failsafe'] vs. Predicted ['compass_interference']