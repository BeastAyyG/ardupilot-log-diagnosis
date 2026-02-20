# ArduPilot AI Log Diagnosis

## What It Does
An agentic AI and rule-based diagnostic engine for analyzing ArduPilot .BIN dataflash logs. Extracts 60+ critical flight telemetry features and uses a hybrid rule/ML intelligence engine to determine whether a flight is healthy or suffering from one of a dozen critical conditions, such as high vibrations, compass interference, and EKF failures.

## Quick Start
```bash
pip install -r requirements.txt
python -m src.cli.main analyze flight.BIN
```

## Sample Output
```
╔═══════════════════════════════════════╗
║  ArduPilot Log Diagnosis Report       ║
╠═══════════════════════════════════════╣
║  Log:      flight.BIN                 ║
║  Duration: 5m 42s                     ║
║  Vehicle:  ArduCopter 4.5.1           ║
╚═══════════════════════════════════════╝

CRITICAL — VIBRATION_HIGH (95%)
  vibe_z_max = 67.8 (limit: 30.0)
  vibe_clip_total = 145 (limit: 0)
  Method: rule + ML
  Fix: Balance/replace propellers.

Overall: NOT SAFE TO FLY
```

## Features Extracted
- **Vibration**: vibe_x/y/z_mean, max, std
- **Compass**: mag_field_mean, range, std
- **Power**: bat_volt_min, max, curr_mean
- **GPS**: hdop_mean, nsats_min
- **Motors**: spread_max, hover_ratio
- **EKF**: variances, lane switches
- **Control**: alt_error, thrust ratio

## Benchmark Results (v0.1.1)
  
Tested against 10 real crash logs from discuss.ardupilot.org with expert-verified diagnoses.

```
╔═════════════════════════════════════════╗
║  ArduPilot Log Diagnosis Benchmark      ║
║  Engine: rules/ml hybrid v0.1.1         ║
╠═════════════════════════════════════════╣
║  Total logs:     10                     ║
║  Extracted:      10 (100%)              ║
║  Macro F1:       0.70                   ║
╚═════════════════════════════════════════╝

Per-Label Results:
┌──────────────────────┬────┬────┬──────┬─────┐
│ Label                │ N  │ TP │ Prec │ F1  │
├──────────────────────┼────┼────┼──────┼─────┤
│ vibration_high       │  5 │  4 │ .66  │ .72 │
│ compass_interference │  5 │  3 │ .75  │ .66 │
└──────────────────────┴────┴────┴──────┴─────┘
```

**Analysis:** 
- 100% stable parser (never crashed)
- Implementation of **Top-1 Confidence Isolation** successfully mitigated the "Symptom Cascade" bottleneck (where vibration shakes compass rendering it a false-positive compass failure).
- Macro F1 surged from `0.20` to `0.70` simply by forcing the ML model to enforce hierarchical diagnosis and disregarding static thresholds if the XGBoost layers strongly disagreed.
- Finding the root-cause vs symptom relationship algorithmically remains the focus of the GSoC ML training phase.

See `benchmark_results.md` for full analysis.

## Benchmarking Execution
```bash
python -m src.cli.main benchmark
```

## Current Limitations
- Rule-based testing only available until ML dataset is generated
- ML model degrading gracefully without missing files
- Precision drops in multi-label scenarios due to un-mapped causal chains

## Contributing Logs
See `download_logs.md` for how to add crash logs to the benchmark dataset.
