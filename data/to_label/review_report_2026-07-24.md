# Candidate Review Report — 2026-07-24

The review cross-checked SHA-deduplicated telemetry candidates against the
original ArduPilot forum incidents. Automatic rule output was treated as a
screening signal, not as ground truth.

## Approved

| File | Final label | Basis |
|---|---|---|
| `log_0049_oscillation_crash.bin` | `motor_imbalance` | Motor spread max 799 and mean 576.16. Forum experts identified Motor 1 failure and an ESC/motor fault. The original automatic `power_instability` label was corrected. |
| `log_0064_flyaway.bin` | `motor_imbalance` | Motor spread max 819 and mean 363.72. Forum experts identified a large rear weight imbalance, with motors 1/3 doing little and motors 2/4 near maximum. |

## Rejected or retained as unverified

| File | Automatic label | Review result |
|---|---|---|
| `log_0028_battery_failsafe.bin` | `power_instability` | Telemetry supports voltage sag, but the forum incident does not establish power instability as the root cause. |
| `log_0030_battery_failsafe.bin` | `power_instability` | Rejected: ArduPilot developer analysis identifies an RC failsafe as the cause of RTL. |
| `log_0048_oscillation_crash.bin` | `power_instability` | Rejected: owner reports healthy batteries; discussion centers on ESC limiting/thrust response and oscillation. |
| `log_0052_oscillation_crash.bin` | `motor_imbalance` | Rejected: fixed-wing tuning/oscillation incident; channel spread is not evidence of multirotor motor imbalance. |
| `log_0056_oscillation_crash.bin` | `power_instability` | Retained unverified: expert suspects Li-ion voltage sag triggering ESC cutoff, but explicitly presents it as a hypothesis and the causal engine ranks vibration/EKF symptoms. |
| `log_0057_oscillation_crash.bin` | `power_instability` | Rejected: this attachment is a disarmed setup log, not the crash flight. |
| `log_0059_flyaway.bin` | `power_instability` | Rejected: discussion identifies bad tuning, vibration, GPS readiness, and pilot throttle handling. |
| `log_0062_flyaway.bin` | `motor_imbalance` | Rejected: discussion identifies extreme vibration, bad tuning, poor GPS readiness, and pilot input; motor imbalance was only a warning. |
| `log_0063_flyaway.bin` | `power_instability` | Rejected: forum analysis shows the climb was commanded by RC throttle and GPS position was followed. |
| `log_0068_uncontrolled_descent.bin` | `power_instability` | Rejected: expert analysis identifies an accelerometer failure. |
| `40.BIN` | `power_instability` | Rejected: incident conclusion identifies an RC failsafe configuration/control-link loss. |

## Promotion rule

Only entries with `human_verified: true` in
`provisional_auto_labels_next.json` may be promoted. All rejected or ambiguous
entries remain excluded from training.
