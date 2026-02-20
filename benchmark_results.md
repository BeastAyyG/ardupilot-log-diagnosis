# Benchmark Results

## Overall Metrics
- Total logs: 10
- Successful Extractions: 10
- Failed Extractions: 0
- Exact Match Accuracy: 0.10
- Macro F1 Score: 0.20

## Per-Label Metrics
| Label | N | TP | Precision | F1 |
|---|---|---|---|---|
| vibration_high | 5 | 4 | 0.50 | 0.62 |
| compass_interference | 5 | 5 | 0.62 | 0.77 |
| power_instability | 0 | 0 | 0.00 | 0.00 |
| motor_imbalance | 0 | 0 | 0.00 | 0.00 |
| ekf_failure | 0 | 0 | 0.00 | 0.00 |
| mechanical_failure | 0 | 0 | 0.00 | 0.00 |
| crash_unknown | 0 | 0 | 0.00 | 0.00 |

## Confusion Details
- **crash_001.BIN**: Expected ['vibration_high'] vs. Predicted ['vibration_high', 'mechanical_failure']
- **crash_002.BIN**: Expected ['vibration_high'] vs. Predicted ['mechanical_failure', 'compass_interference', 'vibration_high', 'motor_imbalance', 'power_instability', 'ekf_failure']
- **crash_003.BIN**: Expected ['vibration_high'] vs. Predicted ['crash_unknown', 'vibration_high', 'motor_imbalance']
- **crash_004.BIN**: Expected ['vibration_high'] vs. Predicted ['compass_interference', 'vibration_high', 'crash_unknown', 'motor_imbalance', 'ekf_failure']
- **crash_005.BIN**: Expected ['vibration_high'] vs. Predicted ['compass_interference', 'motor_imbalance']
- **crash_006.BIN**: Expected ['compass_interference'] vs. Predicted ['ekf_failure', 'compass_interference', 'motor_imbalance', 'vibration_high']
- **crash_008.BIN**: Expected ['compass_interference'] vs. Predicted ['ekf_failure', 'compass_interference', 'vibration_high']
- **crash_009.BIN**: Expected ['compass_interference'] vs. Predicted ['compass_interference', 'vibration_high', 'crash_unknown', 'motor_imbalance', 'ekf_failure']
- **crash_010.BIN**: Expected ['compass_interference'] vs. Predicted ['compass_interference', 'vibration_high', 'crash_unknown', 'motor_imbalance', 'ekf_failure']