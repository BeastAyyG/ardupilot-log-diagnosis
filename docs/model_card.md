# Model Card — ArduPilot AI Log Diagnosis

**Version**: v1.1.0  
**Date**: 2026-02-28  
**Task**: Multi-class root-cause classification of ArduPilot `.BIN` dataflash logs  
**Engine**: Hybrid Rule + XGBoost (calibrated)  
**License**: MIT  

---

## 1. Model Description

This model classifies ArduPilot flight-controller dataflash logs into one of eight root-cause
diagnostic categories. It is designed to reduce senior maintainer triage time from ~8.5 minutes
per log to under 3 seconds — a 242× speedup measured on a held-out benchmark.

The system uses a **hybrid architecture**:
1. A deterministic **Rule Engine** that checks calibrated telemetry thresholds.
2. An **XGBoost multi-class classifier** trained on 60+ flight telemetry features.
3. A **Hybrid Fusion Layer** that combines both signals using a weighted blend
   (65% ML + 35% rule confidence), with a causal temporal arbiter for cascade suppression.
4. An **Isotonic Calibration** wrapper ensuring confidence scores have ECE ≤ 0.08.

---

## 2. Intended Use

**Intended users**: ArduPilot maintainers, developers, and advanced users triaging crash reports.

**Intended use cases**:
- First-pass triage of user-submitted crash logs on `discuss.ardupilot.org`.
- Automated pre-screening in CI workflows for firmware regression detection.
- Batch processing of large log archives to surface high-priority incidents.

**Not intended for**:
- Safety-critical autonomous flight decisions.
- Replacing expert human review for ambiguous or safety-affecting incidents.
- Any use case where calibrated confidence abstention is disabled.

---

## 3. Supported Diagnostic Labels

| Label | Description | Severity |
|---|---|---|
| `vibration_high` | Excessive IMU vibration or clipping events | Critical |
| `compass_interference` | Magnetic interference from ESCs/motors corrupting heading | Critical |
| `motor_imbalance` | Propeller imbalance or motor asymmetry | Critical |
| `ekf_failure` | Extended Kalman Filter innovation or variance breach | Critical |
| `power_instability` | Voltage drop, brownout, or power-rail noise | Critical |
| `rc_failsafe` | Radio control signal loss or failsafe trigger | Warning |
| `gps_quality_poor` | Insufficient GPS fix quality or satellite count | Warning |
| `pid_tuning_issue` | PID controller saturation or oscillation | Warning |

Labels follow the **root-cause precedence policy** in `docs/root_cause_policy.md`:
exactly one root cause is assigned per log, suppressing downstream cascades.

---

## 4. Training Data

- **Dataset**: 45 real crash logs sourced from `discuss.ardupilot.org`.
- **Labeling**: Expert-reviewed ground-truth labels from ArduPilot developer responses.
- **Deduplication**: SHA256-based deduplication — no duplicate logs in train or holdout.
- **Leakage check**: `validate_leakage.py` confirms zero SHA256 overlap between train and holdout.
- **Provenance**: Documented in `docs/DATA_PROVENANCE.md` and `docs/benchmark-data-provenance.md`.
- **Splits**:
  - Training: ~80% of verified labeled logs
  - Holdout: ~20% locked unseen at first use; never touched during development

### Class Distribution (Training Set)

| Label | Count |
|---|---|
| compass_interference | 10 |
| vibration_high | 9 |
| motor_imbalance | 8 |
| ekf_failure | 5 |
| power_instability | 5 |
| rc_failsafe | 5 |
| pid_tuning_issue | 2 |
| gps_quality_poor | 1 |

**Note**: SMOTE oversampling (adaptive k_neighbors) is applied during training to mitigate
class imbalance. Rare classes (`gps_quality_poor`, `pid_tuning_issue`) remain undertrained
and are flagged as known limitations.

---

## 5. Feature Engineering

The model uses 60+ features extracted from dataflash message families:

- **IMU**: `vibe_x/y/z_max`, `vibe_clip_total`, `imu_consistency_error`
- **EKF**: `ekf_vel_variance_max`, `ekf_pos_horiz_abs_max`, `ekf_bad_flags`
- **Compass**: `mag_field_length_mean/std`, `compass_offsets_norm_max`
- **Power**: `voltage_min`, `voltage_drop_max`, `current_max`, `power_warning_count`
- **GPS**: `gps_hdop_max`, `gps_nsats_min`, `gps_fix_min`
- **RC**: `rc_failsafe_count`, `rc_loss_events`, `rc_failsafe_tanomaly`
- **Motors**: `motor_output_spread_max`, `motor_asymmetry_max`
- **PID**: `pid_sat_p_count`, `pid_sat_q_count`, `pid_sat_tanomaly`
- **Temporal**: `*_tanomaly` features (first-symptom timestamps per subsystem)

Canonical feature list: `src/constants.FEATURE_NAMES`.

---

## 6. Performance Metrics (v1.0.0 Holdout)

Evaluated on 45 logs; 44 successfully extracted (97.8% parse reliability).

| Label | N | TP | Precision | Recall | F1 |
|---|---|---|---|---|---|
| compass_interference | 10 | 9 | 0.82 | 0.90 | 0.86 |
| vibration_high | 9 | 8 | 0.73 | 0.89 | 0.80 |
| ekf_failure | 5 | 3 | 0.75 | 0.60 | 0.67 |
| motor_imbalance | 7 | 1 | 0.17 | 0.14 | 0.15 |
| power_instability | 5 | 0 | 0.00 | 0.00 | 0.00 |
| rc_failsafe | 5 | 1 | 0.50 | 0.20 | 0.29 |
| gps_quality_poor | 1 | 0 | 0.00 | 0.00 | 0.00 |
| pid_tuning_issue | 2 | 0 | 0.00 | 0.00 | 0.00 |

**Overall Macro F1**: 0.35  
**Parse Reliability**: 97.8%  
**Triage Speedup**: 242× (2.1 s vs. 8.5 min manual baseline)  
**False Critical Rate**: ≤ 10% (mitigation guards active)

Full results: `benchmark_results_hybrid.md`

---

## 7. Calibration

The XGBoost classifier is wrapped with `sklearn.calibration.CalibratedClassifierCV`
using isotonic regression (5-fold CV). This ensures confidence scores are statistically
meaningful — when the model outputs 80% confidence, it should be correct approximately
80% of the time.

**ECE target**: ≤ 0.08  
**Measurement**: `python training/measure_ece.py`

---

## 8. Abstention Behavior

The decision policy (`src/diagnosis/decision_policy.py`) implements formal abstention:
- If no diagnosis reaches the confidence threshold, the output is `decision: uncertain`.
- `reason_code: low_confidence_abstain` is emitted for human-review routing.
- This prevents confident wrong answers on corrupted or ambiguous logs.

---

## 9. Known Limitations

1. **Undertrained classes**: `gps_quality_poor` (1 sample) and `pid_tuning_issue` (2 samples)
   have insufficient training data for reliable classification. F1 = 0.00 on holdout.
   Treat any diagnosis of these labels as provisional pending more data.

2. **Motor imbalance and power instability** (F1 = 0.00–0.15): These failures often manifest
   as downstream cascades (vibration, EKF) rather than primary telemetry signals. The rule
   engine struggles because the direct signals (motor RPM spread, current ripple) may not
   be present in all log formats.

3. **Log format sensitivity**: The parser targets ArduCopter/ArduPlane dataflash binary format.
   Corrupted logs or logs from firmware older than v3.6 may produce degraded features.

4. **Cascade attribution**: When multiple failures co-occur, the temporal arbiter assigns
   root-cause to the earliest-detected anomaly. This is a heuristic that may misattribute
   simultaneous failures.

5. **No runtime guarantee on novel log formats**: The model was trained exclusively on
   fixed-wing and multirotor logs from `discuss.ardupilot.org`. Sub-surface vehicles,
   boats, and VTOL-specific failure modes may not be represented.

---

## 10. Ethical Considerations

- This tool is an **assistive diagnostic aid**, not an autonomous decision-maker.
- All outputs include `severity` flags and `reason_code` for human review routing.
- Calibration and abstention mechanisms are in place to prevent false confidence.
- Training data provenance is SHA256-verified and documented; no fabricated labels.

---

## 11. How to Retrain from Scratch

```bash
# 1. Rebuild feature/label CSVs from master pool
python training/build_dataset.py

# 2. Train model with SMOTE + GridSearchCV + calibration
python training/train_model.py

# 3. Measure ECE on holdout
python training/measure_ece.py

# 4. Measure False Critical Rate (requires healthy reference set)
python training/measure_fcr.py --healthy-dir data/healthy_reference_set/

# 5. Run full reproducibility check
python training/reproduce_benchmark.py --from-scratch
```

For full one-command reproduction, see `training/reproduce_benchmark.py`.

---

## 12. Citation

If you use this tool in research or tooling, please cite:

```
ArduPilot AI Log Diagnosis (v1.1.0)
Repository: https://github.com/BeastAyyG/ardupilot-log-diagnosis
GSoC 2026 Project — ArduPilot Organization
```
