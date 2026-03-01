# Data Provenance Proposal
## ArduPilot Log Diagnosis — Discussion Thread ↔ Training Log Mapping
### Author: Agastya Pandey | Date: 2026-03-01 | Version: 1.0

---

## Purpose

This document serves as the **official provenance record** for every `.BIN` log
file used in the ArduPilot AI Log Diagnosis training dataset. Each log is traced
back to its original ArduPilot Discourse thread or GitHub issue, providing:

1. **Full traceability** — any log can be traced to a real incident with community
   discussion, making labels trustworthy and reproducible.
2. **GSoC 2026 evidence** — demonstrates systematic, human-curated data collection
   from the ArduPilot community, not synthetic or random data.
3. **Mentor verification** — mentors can click any link below and confirm the
   label matches what the community diagnosed.
4. **Legal clarity** — all posts on discuss.ardupilot.org are CC BY-NC-SA 4.0.
   GitHub issues are under their respective project licenses.

---

## Dataset Summary

| Metric | Value |
|---|---|
| Unique training logs | **111** |
| ArduPilot Discuss threads | **36** |
| GitHub issues / attachments | **5** |
| Total source threads | **41** |
| Failure classes covered | **9** |
| Total Kaggle disk (all datasets) | **4.94 GB** |
| Training rows (after NaN cleaning) | **52** |
| Model Macro F1 (2026-03-01) | **0.357** |

---

## Thread-to-Log Mapping

> **Column guide:**  
> `#` = index · `Logs` = number of .BIN files from that thread · `Label` = ground-truth failure class  
> Thread URLs are clickable — each was manually reviewed before labeling.

| # | ArduPilot Discuss / GitHub Thread | Logs | Failure Class |
|---|---|---|---|
| 1 | [3-6-7-installed-and-tested-drone-crashed-firmware-issue.../39722](https://discuss.ardupilot.org/t/3-6-7-installed-and-tested-drone-crashed-firmware-issue-or-battery-or-something-else-unable-to-find-out/39722) | 1 | `mechanical_failure` |
| 2 | [3d-printed-10-inch-quad-sudden-unrecoverable-yaw/140246](https://discuss.ardupilot.org/t/3d-printed-10-inch-quad-sudden-unrecoverable-yaw/140246) | 2 | `motor_imbalance` |
| 3 | [3dr-iris-crashed-after-3-successful-waypoints-mission/9269](https://discuss.ardupilot.org/t/3dr-iris-crashed-after-3-successful-waypoints-mission/9269) | 9 | `gps_quality_poor` |
| 4 | [a-problem-about-ekf-variance-and-crash/56863](https://discuss.ardupilot.org/t/a-problem-about-ekf-variance-and-crash/56863) | 2 | `vibration_high` |
| 5 | [ac-copter-3-7-dev-fell-from-the-sky-crash-log/37800](https://discuss.ardupilot.org/t/ac-copter-3-7-dev-fell-from-the-sky-crash-log/37800) | 2 | `power_instability` |
| 6 | [automission-misses-wp2-flyaway-crash/19146](https://discuss.ardupilot.org/t/automission-misses-wp2-flyaway-crash/19146) | 4 | `vibration_high` |
| 7 | [copter-3-4-4-rc1-available-for-beta-testing/13645](https://discuss.ardupilot.org/t/copter-3-4-4-rc1-available-for-beta-testing/13645) | 1 | `mechanical_failure` |
| 8 | [copter-3-4-rc5-possible-imu-or-compass-issues/11636](https://discuss.ardupilot.org/t/copter-3-4-rc5-possible-imu-or-compass-issues/11636) | 3 | `compass_interference` |
| 9 | [copter-crash-althold/60815](https://discuss.ardupilot.org/t/copter-crash-althold/60815) | 4 | `vibration_high` |
| 10 | [crash-after-two-motors-suddenly-stopped/132001](https://discuss.ardupilot.org/t/crash-after-two-motors-suddenly-stopped/132001) | 1 | `motor_imbalance` |
| 11 | [crash-analysis-strange-flight-behavior/33345](https://discuss.ardupilot.org/t/crash-analysis-strange-flight-behavior/33345) | 4 | `compass_interference` |
| 12 | [crash-help-with-bin-analysis/42329](https://discuss.ardupilot.org/t/crash-help-with-bin-analysis/42329) | 4 | `vibration_high` |
| 13 | [crash-hexacopter-suddenly-crashed-while-auto/83521](https://discuss.ardupilot.org/t/crash-hexacopter-suddenly-crashed-while-auto/83521) | 4 | `vibration_high` |
| 14 | [crash-with-4-0-0-rc3/50267](https://discuss.ardupilot.org/t/crash-with-4-0-0-rc3/50267) | 2 | `motor_imbalance`, `power_instability` |
| 15 | [ekf-yaw-reset-crash/107273](https://discuss.ardupilot.org/t/ekf-yaw-reset-crash/107273) | 2 | `compass_interference` |
| 16 | [ekf3-position-still-going-mad-in-beta5-drone-crashed/73859](https://discuss.ardupilot.org/t/ekf3-position-still-going-mad-in-beta5-drone-crashed/73859) | 4 | `ekf_failure` |
| 17 | [engine-failure-bug-mechanical-or-other/77323](https://discuss.ardupilot.org/t/engine-failure-bug-mechanical-or-other/77323) | 1 | `mechanical_failure` |
| 18 | [esc-desync-issue-hobbywing-xrotor-pro-60a-tmotor-p60/81059](https://discuss.ardupilot.org/t/esc-desync-issue-hobbywing-xrotor-pro-60a-tmotor-p60/81059) | 1 | `motor_imbalance` |
| 19 | [esc-failure-or-signal-lost-thank-s-for-help/18093](https://discuss.ardupilot.org/t/esc-failure-or-signal-lost-thank-s-for-help/18093) | 2 | `mechanical_failure` |
| 20 | [fixed-wing-dead-reckoning-test-zealot-h743-aero/101680](https://discuss.ardupilot.org/t/fixed-wing-dead-reckoning-test-of-the-zealot-h743-aero-applications-edition/101680) | 4 | `mechanical_failure` |
| 21 | [hexacopter-drifting-away-crash-log-video/26675](https://discuss.ardupilot.org/t/hexacopter-drifting-away-crash-log-video/26675) | 7 | `compass_interference` |
| 22 | [hexacopter-redundancy/72447](https://discuss.ardupilot.org/t/hexacopter-redundancy/72447) | 1 | `mechanical_failure` |
| 23 | [how-to-make-yaw-roll-and-pitch-smoother/64483](https://discuss.ardupilot.org/t/how-to-make-yaw-roll-and-pitch-smoother/64483) | 5 | `pid_tuning_issue` |
| 24 | [is-there-a-vibration-issue-here/15264](https://discuss.ardupilot.org/t/is-there-a-vibration-issue-here/15264) | 4 | `vibration_high` |
| 25 | [large-10kg-payload-drone-crash-on-take-off/11083](https://discuss.ardupilot.org/t/large-10kg-payload-drone-crash-on-take-off-please-help/11083) | 2 | `power_instability` |
| 26 | [loiter-issue-no-mag-data-bad-motor-balance/18364](https://discuss.ardupilot.org/t/loiter-issue-no-mag-data-bad-motor-balance/18364) | 2 | `power_instability` |
| 27 | [loiter-mode-climb-drift-and-crash/7594](https://discuss.ardupilot.org/t/loiter-mode-climb-drift-and-crash/7594) | 4 | `vibration_high` |
| 28 | [major-ek2-fail-and-big-crash/19650](https://discuss.ardupilot.org/t/major-ek2-fail-and-big-crash/19650) | 4 | `compass_interference` |
| 29 | [motor-turned-off-in-mid-flight/121845](https://discuss.ardupilot.org/t/motor-turned-off-in-mid-flight/121845) | 1 | `motor_imbalance` |
| 30 | [no-rc-receiver-lockup-between-flight-controller-and-receiver/45811](https://discuss.ardupilot.org/t/no-rc-receiver-lockup-between-flight-controller-and-receiver/45811) | 2 | `rc_failsafe` |
| 31 | [pixhawk-1-midair-reboot/17918](https://discuss.ardupilot.org/t/pixhawk-1-midair-reboot/17918) | 1 | `power_instability` |
| 32 | [pixhawk-clone-2-4-8-motors-not-running-same-speed/93719](https://discuss.ardupilot.org/t/pixhawk-clone-2-4-8-motors-not-running-in-the-same-speed/93719) | 2 | `rc_failsafe` |
| 33 | [radio-failsafe-during-operation/101055](https://discuss.ardupilot.org/t/radio-failsafe-during-operation/101055) | 4 | `rc_failsafe` |
| 34 | [stil-fw-4-2-0dev-crashes-ahrs-ekf3-lane-switch/77702](https://discuss.ardupilot.org/t/stil-fw-4-2-0dev-crashes-the-plane-with-ahrs-ekf3-lane-switch-0-message/77702) | 2 | `ekf_failure` |
| 35 | [unstable-drone-after-takeoff-crashes/43780](https://discuss.ardupilot.org/t/unstable-drone-after-takeoff-crashes/43780) | 4 | `vibration_high` |
| 36 | [yaw-instability-and-crash-high-vibrations-motor-imbalance/130060](https://discuss.ardupilot.org/t/yaw-instability-and-crash-in-loiter-mode-high-vibrations-motor-imbalance-issues/130060) | 1 | `motor_imbalance` |
| 37 | [potential-thrust-loss/142590](https://discuss.ardupilot.org/t/potential-thrust-loss/142590) ⭐ | 1 | `motor_imbalance` |
| 38 | [GitHub issue #7119 — ardupilot/ardupilot](https://github.com/ArduPilot/ardupilot/issues/7119) | 1 | `ekf_failure` |
| 39 | [GitHub issue #8931 — ardupilot/ardupilot](https://github.com/ArduPilot/ardupilot/issues/8931) | 2 | `ekf_failure` |
| 40 | [GitHub attachment — bug_report_1.zip](https://github.com/ArduPilot/ardupilot/files/12009217/bug_report_1.zip) | 1 | `ekf_failure` |
| 41 | [GitHub attachment — bin_and_telemetry_logs.zip](https://github.com/ArduPilot/ardupilot/files/12101758/bin_and_telemetry_logs.zip) | 1 | `ekf_failure` |

> ⭐ = Wild holdout log (SHA-verified never seen in training, correct
> diagnosis: `MOTOR_IMBALANCE 85% CONFIRMED` vs forum user report "Motor 2 runs hot")

---

## Failure Class Coverage

| Failure Class | Training Logs | Threads | Key Evidence Features |
|---|---|---|---|
| `vibration_high` | 29 | 9 | `vibe_z_max`, `vibe_clip_total`, `fft_peak_hz` |
| `compass_interference` | 27 | 7 | `mag_field_range`, `mag_field_std` |
| `rc_failsafe` | 13 | 4 | `evt_rc_failsafe_count`, `rc_signal_lost_pct` |
| `ekf_failure` | 11 | 6 | `ekf_vel_var_max`, `ekf_pos_var_max` |
| `motor_imbalance` | 8 | 7 | `motor_spread_max`, `motor_spread_mean` |
| `power_instability` | 8 | 5 | `bat_volt_range`, `bat_curr_max` |
| `pid_tuning_issue` | 6 | 1 | `attitude_error_roll_max`, `pid_p_std` |
| `gps_quality_poor` | 7 | 1 | `gps_hdop_mean`, `gps_nsats_min` |
| `mechanical_failure` | 10 | 7 | `motor_spread_max`, `ekf_vel_var_max` |

---

## Labeling Methodology

Each log was labeled using the following hierarchy:

```
Priority 1: Expert community diagnosis (forum replies from experienced pilots)
Priority 2: ArduPilot developer diagnosis (GitHub issue comments)
Priority 3: Hybrid engine confirmation (rule engine + feature analysis)
Priority 4: Filename pattern (lowest trust — used only for unlabeled to_label/ batch)
```

All labels are stored in per-batch `ground_truth.json` files under `data/clean_imports/`.

---

## Provisional Auto-Labels (Not in Training)

The **35 unlabeled logs** in `data/to_label/` were processed by the hybrid engine
on 2026-03-01. Results saved to `data/to_label/provisional_auto_labels_2026-03-01.json`.

| Status | Count |
|---|---|
| High-confidence (≥65%) auto-labeled | 22 |
| Low-confidence (<65%) — needs review | 10 |
| No diagnosis | 1 |
| Parse failed | 1 |

**None of these are in the training set.** To promote: set `human_verified: true`
in the provisional file, then run `python3 training/promote_verified_labels.py`.

---

## Reproducibility

To regenerate the training dataset from scratch:

```bash
# 1. Download all logs (Kaggle API)
python3 -c "
import os; os.environ['KAGGLE_CONFIG_DIR']='/home/ayyg/Downloads'
import kagglehub
kagglehub.dataset_download('beastayyg/ardupilot-complete-raw-data-backup-2026')
kagglehub.dataset_download('beastayyg/ardupilot-master-log-pool-v2')
"

# 2. Build features from all labeled logs
python3 training/build_dataset.py \
  --ground-truth /tmp/unified_ground_truth.json \
  --dataset-dir  data/kaggle_backups/ardupilot-master-log-pool-v2

# 3. Train the model
python3 training/train_model.py

# 4. Verify on wild holdout
python3 -m src.cli.main analyze /path/to/forum_log.bin
# Expected: MOTOR_IMBALANCE 85% CONFIRMED
```

---

## Citation

If using this dataset in any publication or project:

```
Pandey, A. (2026). ArduPilot Log Diagnosis Training Dataset.
Curated from ArduPilot Community Forum (discuss.ardupilot.org),
41 threads, 111 unique BIN logs, 9 failure classes.
Kaggle: https://www.kaggle.com/datasets/beastayyg/ardupilot-master-log-pool-v2
```

---

*Document generated: 2026-03-01 | SRM University AP | GSoC 2026 Application*
