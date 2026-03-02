# Benchmark Results

## Overall Metrics
- Total logs: 10
- Successful Extractions: 5
- Failed Extractions: 5
- Exact Match Accuracy: 0.00
- Macro F1 Score: 0.00

## Per-Label Metrics
| Label | N | TP | Precision | F1 |
|---|---|---|---|---|
| vibration_high | 0 | 0 | 0.00 | 0.00 |
| motor_imbalance | 0 | 0 | 0.00 | 0.00 |
| mechanical_failure | 5 | 0 | 0.00 | 0.00 |
| brownout | 0 | 0 | 0.00 | 0.00 |
| thrust_loss | 0 | 0 | 0.00 | 0.00 |

## Confusion Details
- **log_0044_mechanical_failure.bin**: Expected ['mechanical_failure'] vs. Predicted ['motor_imbalance', 'brownout']
- **log_0045_mechanical_failure.bin**: Expected ['mechanical_failure'] vs. Predicted ['motor_imbalance', 'brownout', 'thrust_loss']
- **log_0043_mechanical_failure.bin**: Expected ['mechanical_failure'] vs. Predicted ['motor_imbalance', 'thrust_loss']
- **log_0036_mechanical_failure.bin**: Expected ['mechanical_failure'] vs. Predicted ['motor_imbalance', 'vibration_high']
- **log_0042_mechanical_failure.bin**: Expected ['mechanical_failure'] vs. Predicted ['motor_imbalance', 'vibration_high', 'thrust_loss']