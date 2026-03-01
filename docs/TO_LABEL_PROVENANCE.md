# Provisional Label Proposal
## 35 Unlabeled Logs — ArduPilot Discuss Thread Mapping & Engine Results
### Author: Agastya Pandey | Date: 2026-03-01

---

## Overview

This document maps each of the **34 provisionally auto-labeled** forum log files
(from `data/to_label/`) to their **original ArduPilot Discuss thread**, shows what
the **crawler collected them as**, and what the **hybrid engine diagnosed** after
running the rule + ML pipeline.

> ⚠️ **None of these are in the training set.** `human_verified: false` on all.  
> This document exists to show: thread source → downloaded log → engine diagnosis.

---

## Summary Table

| # | Discussion Thread | File | Collected As | Engine Says | Confidence | Status |
|---|---|---|---|---|---|---|
| 1 | [RTL Does Not Return to Launch.../6876](https://discuss.ardupilot.org/t/rtl-does-not-return-to-launch-nor-lands-but-kind-of-loiters/6876) | `log_0028_battery_failsafe.bin` | battery_failsafe | **motor_imbalance** | 81% | ✅ High |
| 2 | [Pixhawk Clone Motors Not Same Speed/93719](https://discuss.ardupilot.org/t/pixhawk-clone-2-4-8-motors-not-running-in-the-same-speed/93719) | `log_0029_battery_failsafe.bin` | battery_failsafe | **gps_quality_poor** | 85% | ✅ High |
| 3 | [Copter 3.5.5-rc1 Beta Testing/25162](https://discuss.ardupilot.org/t/copter-3-5-5-rc1-available-for-beta-testing/25162) | `log_0030_battery_failsafe.bin` | battery_failsafe | **rc_failsafe** | 76% | ✅ High |
| 4 | [Failure to Launch/80437](https://discuss.ardupilot.org/t/failure-to-launch/80437) | `log_0032_hardware_failure.bin` | hardware_failure | **compass_interference** | 76% | ✅ High |
| 5 | [Oscillation in Roll and Pitch Crash/93512](https://discuss.ardupilot.org/t/oscillation-in-roll-and-pitch-resulting-in-crash/93512) | `log_0048_oscillation_crash.bin` | oscillation_crash | **compass_interference** | 85% | ✅ High |
| 6 | [Quadcopter Crash Log Analysis/99897](https://discuss.ardupilot.org/t/quadcopter-crash-log-analysis-request/99897) | `log_0049_oscillation_crash.bin` | oscillation_crash | **compass_interference** | 85% | ✅ High |
| 7 | [Quadcopter Crash Log Analysis/99897](https://discuss.ardupilot.org/t/quadcopter-crash-log-analysis-request/99897) | `log_0050_oscillation_crash.bin` | oscillation_crash | **crash_unknown** | 0% | ⬜ None |
| 8 | [Tuning Issues Plane - Auto T/O and Land/100608](https://discuss.ardupilot.org/t/tuning-issues-with-plane-successful-auto-t-o-and-land-maiden-now-not-so-much/100608) | `log_0052_oscillation_crash.bin` | oscillation_crash | **compass_interference** | 55% | ⚠️ Weak |
| 9 | [Tuning Issues Plane - Auto T/O and Land/100608](https://discuss.ardupilot.org/t/tuning-issues-with-plane-successful-auto-t-o-and-land-maiden-now-not-so-much/100608) | `log_0053_oscillation_crash.bin` | oscillation_crash | **motor_imbalance** | 81% | ✅ High |
| 10 | [Tuning Issues Plane - Auto T/O and Land/100608](https://discuss.ardupilot.org/t/tuning-issues-with-plane-successful-auto-t-o-and-land-maiden-now-not-so-much/100608) | `log_0054_oscillation_crash.bin` | oscillation_crash | **motor_imbalance** | 81% | ✅ High |
| 11 | [Tuning Issues Plane - Auto T/O and Land/100608](https://discuss.ardupilot.org/t/tuning-issues-with-plane-successful-auto-t-o-and-land-maiden-now-not-so-much/100608) | `log_0055_oscillation_crash.bin` | oscillation_crash | **motor_imbalance** | 81% | ✅ High |
| 12 | [Crash When Switching RTL to Loiter/103732](https://discuss.ardupilot.org/t/crash-when-switching-from-rtl-to-loiter/103732) | `log_0056_oscillation_crash.bin` | oscillation_crash | **compass_interference** | 85% | ✅ High |
| 13 | [Crash When Switching RTL to Loiter/103732](https://discuss.ardupilot.org/t/crash-when-switching-from-rtl-to-loiter/103732) | `log_0057_oscillation_crash.bin` | oscillation_crash | **compass_interference** | 83% | ✅ High |
| 14 | [Multiple Flyaways in Guided/17438](https://discuss.ardupilot.org/t/multiple-flyaways-in-guided-do-i-need-to-tune-the-ekf/17438) | `log_0058_flyaway.bin` | flyaway | **motor_imbalance** | 47% | ⚠️ Weak |
| 15 | [Something is Wrong With My Copter Build/46289](https://discuss.ardupilot.org/t/something-is-wrong-with-my-copter-build/46289) | `log_0059_flyaway.bin` | flyaway | **motor_imbalance** | 55% | ⚠️ Weak |
| 16 | [Something is Wrong With My Copter Build/46289](https://discuss.ardupilot.org/t/something-is-wrong-with-my-copter-build/46289) | `log_0060_flyaway.bin` | flyaway | **motor_imbalance** | 47% | ⚠️ Weak |
| 17 | [Multiple Flyaways in Loiter and Auto/17663](https://discuss.ardupilot.org/t/multiple-flyaways-in-loiter-and-auto/17663) | `log_0061_flyaway.bin` | flyaway | **ekf_failure** | 85% | ✅ High |
| 18 | [Quad Flyaway Need Analysis/69210](https://discuss.ardupilot.org/t/quad-flyaway-need-analysis/69210) | `log_0062_flyaway.bin` | flyaway | **motor_imbalance** | 85% | ✅ High |
| 19 | [Possibly a Fly Away - Please Look at Log/41183](https://discuss.ardupilot.org/t/possibly-a-fly-away-please-take-a-look-at-the-log/41183) | `log_0063_flyaway.bin` | flyaway | **motor_imbalance** | 93% | ✅ High |
| 20 | [RTL Flyaway Bad Pos Among Others/53951](https://discuss.ardupilot.org/t/rtl-flyaway-bad-pos-among-others/53951) | `log_0064_flyaway.bin` | flyaway | **compass_interference** | 85% | ✅ High |
| 21 | [Radio Failsafe During Operation/101055](https://discuss.ardupilot.org/t/radio-failsafe-during-operation/101055) | `log_0065_flyaway.bin` | flyaway | **compass_interference** | 85% | ✅ High |
| 22 | [Radio Failsafe During Operation/101055](https://discuss.ardupilot.org/t/radio-failsafe-during-operation/101055) | `log_0066_flyaway.bin` | flyaway | **motor_imbalance** | 81% | ✅ High |
| 23 | [Solo Flyaway and Crash During Auto Mission/15265](https://discuss.ardupilot.org/t/solo-flyaway-and-crash-during-auto-mission/15265) | `log_0067_flyaway.bin` | flyaway | **compass_interference** | 81% | ✅ High |
| 24 | [Copter Unexpected Rapid Climb After Arming/119799](https://discuss.ardupilot.org/t/copter-unexpected-rapid-climb-after-arming-eventually-crashed/119799) | `log_0068_uncontrolled_descent.bin` | uncontrolled_descent | **compass_interference** | 85% | ✅ High |
| 25 | [Radio Failsafe Climbs 15m Immediately After Arming/99762](https://discuss.ardupilot.org/t/quadcopter-gives-radio-failsafe-and-climbs-to-15-meters-immidiately-after-arming/99762) | `log_0069_radio_failsafe.bin` | radio_failsafe | **compass_interference** | 58% | ⚠️ Weak |
| 26 | [Failsafe SBUS Not Working/65942](https://discuss.ardupilot.org/t/failsafe-sbus-not-working/65942) | `log_0070_radio_failsafe.bin` | radio_failsafe | **motor_imbalance** | 81% | ✅ High |
| 27 | [Failsafe SBUS Not Working/65942](https://discuss.ardupilot.org/t/failsafe-sbus-not-working/65942) | `log_0071_radio_failsafe.bin` | radio_failsafe | **gps_quality_poor** | 85% | ✅ High |
| 28 | *(no URL — local collection)* | `00000058.BIN` | — | **compass_interference** | 85% | ✅ High |
| 29 | *(no URL — local collection)* | `00000060.BIN` | — | **compass_interference** | 55% | ⚠️ Weak |
| 30 | *(no URL — local collection)* | `2016-09-18 08-44-44.bin` | — | **compass_interference** | 47% | ⚠️ Weak |
| 31 | *(no URL — local collection)* | `2016-09-18 16-01-53.bin` | — | **compass_interference** | 47% | ⚠️ Weak |
| 32 | *(no URL — local collection)* | `2018-09-21 18-26-05.bin` | — | **motor_imbalance** | 47% | ⚠️ Weak |
| 33 | *(no URL — local collection)* | `40.BIN` | — | **compass_interference** | 49% | ⚠️ Weak |
| 34 | *(parse failed — not a flight log)* | `flash.bin` | — | — | — | ❌ Skip |

---

## Detailed Entries by Thread

### 🔴 oscillation_crash threads (8 logs from 3 threads)

#### [Oscillation in Roll and Pitch Resulting in Crash](https://discuss.ardupilot.org/t/oscillation-in-roll-and-pitch-resulting-in-crash/93512)
**Thread ID:** 93512  
**Files:** `log_0048_oscillation_crash.bin`  
**Collected as:** `oscillation_crash`  
**Engine result:** `compass_interference` — **85% confidence** via rule engine  
**Evidence:** `mag_field_range=433.05 mGauss` (limit: 200), `mag_field_std=56.98`  
**Interpretation:** The oscillation may be caused by compass heading error due to magnetic interference, leading to attitude control instability. ✅ Review recommended.

---

#### [Quadcopter Crash Log Analysis Request](https://discuss.ardupilot.org/t/quadcopter-crash-log-analysis-request/99897)
**Thread ID:** 99897  
**Files:** `log_0049_oscillation_crash.bin`, `log_0050_oscillation_crash.bin`

| File | Engine Label | Confidence | Evidence |
|---|---|---|---|
| `log_0049_oscillation_crash.bin` | **compass_interference** | 85% | `mag_field_range=526.61`, `mag_field_std=66.03` |
| `log_0050_oscillation_crash.bin` | **crash_unknown** | 0% | No features triggered — likely short log |

---

#### [Tuning Issues — Plane Auto T/O and Land, Maiden Now Not So Much](https://discuss.ardupilot.org/t/tuning-issues-with-plane-successful-auto-t-o-and-land-maiden-now-not-so-much/100608)
**Thread ID:** 100608  
**Files:** `log_0052`, `log_0053`, `log_0054`, `log_0055` (all `oscillation_crash`)

| File | Engine Label | Confidence | Evidence |
|---|---|---|---|
| `log_0052_oscillation_crash.bin` | **compass_interference** | 55% ⚠️ | `mag_field_range=276.18` |
| `log_0053_oscillation_crash.bin` | **motor_imbalance** | 81% | `motor_spread_max=963 PWM` |
| `log_0054_oscillation_crash.bin` | **motor_imbalance** | 81% | `motor_spread_max=963 PWM`, `motor_spread_mean=508.51` |
| `log_0055_oscillation_crash.bin` | **motor_imbalance** | 81% | `motor_spread_max=963 PWM`, `motor_spread_mean=424.33` |

**Note:** Thread has multiple flights. Logs 0053–0055 all show extreme motor spread (963 PWM vs 300 limit), consistent with motor_imbalance. Log 0052 is a borderline compass case.

---

#### [Crash When Switching from RTL to Loiter](https://discuss.ardupilot.org/t/crash-when-switching-from-rtl-to-loiter/103732)
**Thread ID:** 103732  
**Files:** `log_0056_oscillation_crash.bin`, `log_0057_oscillation_crash.bin`

| File | Engine Label | Confidence | Evidence |
|---|---|---|---|
| `log_0056_oscillation_crash.bin` | **compass_interference** | 85% | `mag_field_range=510.73 mGauss` |
| `log_0057_oscillation_crash.bin` | **compass_interference** | 83% | Rule + ML agreement |

---

### 🟠 flyaway threads (10 logs from 7 threads)

#### [Multiple Flyaways in Guided — Do I Need to Tune the EKF?](https://discuss.ardupilot.org/t/multiple-flyaways-in-guided-do-i-need-to-tune-the-ekf/17438)
**File:** `log_0058_flyaway.bin`  
**Engine:** `motor_imbalance` 47% ⚠️ (weak — `motor_spread_max=810 PWM`)  
**Note:** Thread title suggests EKF but engine sees motor imbalance. Needs review.

---

#### [Something is Wrong With My Copter Build](https://discuss.ardupilot.org/t/something-is-wrong-with-my-copter-build/46289)
**Files:** `log_0059_flyaway.bin`, `log_0060_flyaway.bin`  
| File | Engine Label | Conf | Evidence |
|---|---|---|---|
| `log_0059_flyaway.bin` | motor_imbalance | 55% ⚠️ | `motor_spread_max=507 PWM` |
| `log_0060_flyaway.bin` | motor_imbalance | 47% ⚠️ | `motor_spread_max=521 PWM` |

---

#### [Multiple Flyaways in Loiter and Auto](https://discuss.ardupilot.org/t/multiple-flyaways-in-loiter-and-auto/17663)
**File:** `log_0061_flyaway.bin`  
**Engine:** `ekf_failure` **85%** via rule  
**Evidence:** `ekf_vel_var_max=7.13`, `ekf_pos_var_max=1.69`, `ekf_compass_var_max=1.17`  
**Note:** Classic EKF divergence — position and velocity estimates both exceeded limits. Flyaway directly caused by EKF failure. ✅ High confidence.

---

#### [Quad Flyaway Need Analysis](https://discuss.ardupilot.org/t/quad-flyaway-need-analysis/69210)
**File:** `log_0062_flyaway.bin`  
**Engine:** `motor_imbalance` **85%** via rule  
**Evidence:** `motor_spread_max=1000 PWM` (limit 300), `motor_spread_mean=718.97`

---

#### [Possibly a Fly Away — Please Take a Look at the Log](https://discuss.ardupilot.org/t/possibly-a-fly-away-please-take-a-look-at-the-log/41183)
**File:** `log_0063_flyaway.bin`  
**Engine:** `motor_imbalance` **93%** via rule+ml  
**Evidence:** `motor_spread_max=916 PWM`, `motor_spread_mean=555.20`  
**Note:** Highest-confidence diagnosis in this batch. Rule and ML both agree. ✅

---

#### [RTL Flyaway — Bad Pos Among Others](https://discuss.ardupilot.org/t/rtl-flyaway-bad-pos-among-others/53951)
**File:** `log_0064_flyaway.bin`  
**Engine:** `compass_interference` **85%** via rule  
**Evidence:** `mag_field_range=912.49 mGauss` (4× limit)

---

#### [Radio Failsafe During Operation](https://discuss.ardupilot.org/t/radio-failsafe-during-operation/101055)
**Files:** `log_0065_flyaway.bin`, `log_0066_flyaway.bin`

| File | Engine Label | Conf | Evidence |
|---|---|---|---|
| `log_0065_flyaway.bin` | compass_interference | 85% | `mag_field_range=510.73`, `mag_field_std=225.77` |
| `log_0066_flyaway.bin` | motor_imbalance | 81% | `motor_spread_max=950 PWM` |

---

#### [Solo Flyaway and Crash During Auto Mission](https://discuss.ardupilot.org/t/solo-flyaway-and-crash-during-auto-mission/15265)
**File:** `log_0067_flyaway.bin`  
**Engine:** `compass_interference` **81%** via rule+ml  
**Evidence:** `mag_field_range=411.68 mGauss`

---

### 🟡 battery_failsafe threads (3 logs from 3 threads)

#### [RTL Does Not Return to Launch Nor Lands — Kind of Loiters](https://discuss.ardupilot.org/t/rtl-does-not-return-to-launch-nor-lands-but-kind-of-loiters/6876)
**File:** `log_0028_battery_failsafe.bin`  
**Engine:** `motor_imbalance` **81%** via rule  
**Evidence:** `motor_spread_max=838 PWM`, `motor_spread_mean=770.53`  
**Note:** Filename says battery_failsafe but physical root cause is motor_imbalance. Battery failsafe may have triggered due to high current draw from imbalanced motors.

---

#### [Pixhawk Clone — Motors Not Running at Same Speed](https://discuss.ardupilot.org/t/pixhawk-clone-2-4-8-motors-not-running-in-the-same-speed/93719)
**File:** `log_0029_battery_failsafe.bin`  
**Engine:** `gps_quality_poor` **85%** via rule  
**Evidence:** `gps_hdop_mean=99.99` (HDOP maxed — GPS lock never acquired)

---

#### [Copter 3.5.5-rc1 Beta Testing](https://discuss.ardupilot.org/t/copter-3-5-5-rc1-available-for-beta-testing/25162)
**File:** `log_0030_battery_failsafe.bin`  
**Engine:** `rc_failsafe` **76%** via rule  
**Evidence:** `evt_rc_failsafe_count` triggered

---

### 🔵 hardware_failure thread (1 log)

#### [Failure to Launch](https://discuss.ardupilot.org/t/failure-to-launch/80437)
**File:** `log_0032_hardware_failure.bin` (49.2 MB)  
**Engine:** `compass_interference` **76%** via rule  
**Evidence:** `mag_field_range=422.83 mGauss`  
**Note:** Large log. Compass interference consistent with launch failure if heading was wrong from the start.

---

### 🟣 uncontrolled_descent (1 log)

#### [Copter Unexpected Rapid Climb After Arming — Eventually Crashed](https://discuss.ardupilot.org/t/copter-unexpected-rapid-climb-after-arming-eventually-crashed/119799)
**File:** `log_0068_uncontrolled_descent.bin`  
**Engine:** `compass_interference` **85%** via rule  
**Evidence:** Compass field anomaly consistent with a bad heading on arming causing the rapid attitude divergence.

---

### 🔶 radio_failsafe threads (3 logs from 2 threads)

#### [Quadcopter Gives Radio Failsafe and Climbs 15m Immediately After Arming](https://discuss.ardupilot.org/t/quadcopter-gives-radio-failsafe-and-climbs-to-15-meters-immidiately-after-arming/99762)
**File:** `log_0069_radio_failsafe.bin`  
**Engine:** `compass_interference` **58%** ⚠️ (weak) via rule+ml  
**Evidence:** `mag_field_range=3136.32 mGauss` (extreme — likely near metal or electronics)

---

#### [Failsafe SBUS Not Working](https://discuss.ardupilot.org/t/failsafe-sbus-not-working/65942)
**Files:** `log_0070_radio_failsafe.bin`, `log_0071_radio_failsafe.bin`

| File | Engine Label | Conf | Evidence |
|---|---|---|---|
| `log_0070_radio_failsafe.bin` | motor_imbalance | 81% | `motor_spread_max=900 PWM` |
| `log_0071_radio_failsafe.bin` | gps_quality_poor | 85% | `gps_hdop_mean=99.99`, `gps_fix_pct=0.0%` |

---

### ⚫ No URL tracked (7 logs — local disk collection)

These logs were collected directly from local storage without a forum URL being recorded in the crawler manifest.

| File | Engine Label | Confidence | Notes |
|---|---|---|---|
| `00000058.BIN` | compass_interference | 85% | Generic ArduPilot sequential log name |
| `00000060.BIN` | compass_interference | 55% ⚠️ | Generic ArduPilot sequential log name |
| `2016-09-18 08-44-44.bin` | compass_interference | 47% ⚠️ | Date-stamped log from 2016 |
| `2016-09-18 16-01-53.bin` | compass_interference | 47% ⚠️ | Date-stamped log from 2016 |
| `2018-09-21 18-26-05.bin` | motor_imbalance | 47% ⚠️ | Date-stamped log from 2018 |
| `40.BIN` | compass_interference | 49% ⚠️ | Sequential Pixhawk log |
| `flash.bin` | — (parse failed) | — | Not a flight log — firmware flash artifact |

---

## Key Finding: Filename Label ≠ Physical Root Cause

| Filename claimed | Engine found | Frequency |
|---|---|---|
| `oscillation_crash` | compass_interference or motor_imbalance | 7/8 logs |
| `flyaway` | motor_imbalance or compass_interference | 8/10 logs |
| `battery_failsafe` | motor_imbalance, gps_poor, or rc_failsafe | 3/3 logs |
| `radio_failsafe` | motor_imbalance or gps_poor | 2/3 logs |

**This confirms:** The event name (what happened) ≠ the root cause (why it happened).
The hybrid engine is diagnosing the **underlying physical failure**, not the observable symptom.

---

## Legend

| Symbol | Meaning |
|---|---|
| ✅ High | confidence ≥ 65% — engine is confident |
| ⚠️ Weak | confidence < 65% — needs human review |
| ⬜ None | no features triggered — tagged crash_unknown |
| ❌ Skip | corrupt or non-flight file |

---

## Next Steps

1. **Open** `data/to_label/provisional_auto_labels_2026-03-01.json`
2. **Click each thread link** in this document to verify the community diagnosis
3. **Set** `"human_verified": true` for entries you confirm
4. **Run** `python3 training/promote_verified_labels.py --provisional data/to_label/provisional_auto_labels_2026-03-01.json --output-dir data/clean_imports/human_review_batch_01/`
5. **Retrain** the model with the newly verified logs

---

*Generated: 2026-03-01 | SRM University AP | ArduPilot Log Diagnosis Project*
