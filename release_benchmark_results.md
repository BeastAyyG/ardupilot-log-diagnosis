# Benchmark Results

## Metric Definitions
- Any-Match Accuracy: at least one predicted label matches ground truth.
- Top-1 Accuracy: highest-confidence prediction matches ground truth.
- Exact-Match Accuracy: predicted label set exactly matches ground truth.

## Overall Metrics
- Total logs: 6
- Successful Extractions: 6
- Failed Extractions: 0
- Any-Match Accuracy: 1.00
- Top-1 Accuracy: 1.00
- Exact-Match Accuracy: 0.67
- Macro F1 Score: 0.81

## Per-Label Metrics
| Label | N | TP | Precision | F1 |
|---|---|---|---|---|
| vibration_high | 1 | 1 | 1.00 | 1.00 |
| compass_interference | 2 | 2 | 1.00 | 1.00 |
| power_instability | 2 | 1 | 1.00 | 0.67 |
| motor_imbalance | 3 | 3 | 1.00 | 1.00 |
| ekf_failure | 2 | 2 | 1.00 | 1.00 |
| rc_failsafe | 1 | 1 | 1.00 | 1.00 |
| thrust_loss | 1 | 0 | 0.00 | 0.00 |

## Confusion Details
- **5c454779ec__log_0013_power_instability.bin**: Expected ['motor_imbalance', 'power_instability', 'ekf_failure'] vs. Predicted ['motor_imbalance', 'ekf_failure']
- **log_0046_thrust_loss.bin**: Expected ['thrust_loss', 'motor_imbalance', 'power_instability'] vs. Predicted ['motor_imbalance', 'power_instability']