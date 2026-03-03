# Benchmark Results

## Overall Metrics
- Total logs: 10
- Successful Extractions: 5
- Failed Extractions: 5
- Exact Match Accuracy: 0.80
- Macro F1 Score: 0.18

## Per-Label Metrics
| Label | N | TP | Precision | F1 |
|---|---|---|---|---|
| vibration_high | 0 | 0 | 0.00 | 0.00 |
| motor_imbalance | 0 | 0 | 0.00 | 0.00 |
| mechanical_failure | 5 | 4 | 1.00 | 0.89 |
| brownout | 0 | 0 | 0.00 | 0.00 |
| thrust_loss | 0 | 0 | 0.00 | 0.00 |

## Confusion Details
- **log_0044_mechanical_failure.bin**: Expected ['mechanical_failure'] vs. Predicted ['mechanical_failure', 'motor_imbalance', 'brownout']
- **log_0045_mechanical_failure.bin**: Expected ['mechanical_failure'] vs. Predicted ['mechanical_failure', 'motor_imbalance', 'thrust_loss', 'brownout']
- **log_0043_mechanical_failure.bin**: Expected ['mechanical_failure'] vs. Predicted ['mechanical_failure', 'motor_imbalance', 'thrust_loss']
- **log_0036_mechanical_failure.bin**: Expected ['mechanical_failure'] vs. Predicted ['vibration_high', 'motor_imbalance']
- **log_0042_mechanical_failure.bin**: Expected ['mechanical_failure'] vs. Predicted ['mechanical_failure', 'motor_imbalance', 'vibration_high', 'thrust_loss']