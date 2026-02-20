# Benchmark Results

## Overall Metrics
- Total logs: 10
- Successful Extractions: 10
- Failed Extractions: 0
- Exact Match Accuracy: 0.70
- Macro F1 Score: 0.70

## Per-Label Metrics
| Label | N | TP | Precision | F1 |
|---|---|---|---|---|
| vibration_high | 5 | 4 | 0.67 | 0.73 |
| compass_interference | 5 | 3 | 0.75 | 0.67 |

## Confusion Details
- **crash_005.BIN**: Expected ['vibration_high'] vs. Predicted ['compass_interference']
- **crash_008.BIN**: Expected ['compass_interference'] vs. Predicted ['vibration_high']
- **crash_010.BIN**: Expected ['compass_interference'] vs. Predicted ['vibration_high']