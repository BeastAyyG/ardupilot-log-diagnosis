# Data Request Pack (2026-02-23)

Use this brief with collaborators to source more real ArduPilot DataFlash logs.

## What We Already Have (SHA-Unique, Verified)

- `vibration_high`: 8
- `compass_interference`: 5
- `rc_failsafe`: 4
- `healthy`: 0
- `gps_quality_poor`: 1
- `pid_tuning_issue`: 1
- `power_instability`: 0
- `motor_imbalance`: 0
- `ekf_failure`: 0
- `mechanical_failure`: 0
- `brownout`: 0
- `crash_unknown`: 0

Total unique labeled logs: 19.

## Internal Backlog Ready To Label Now

There are 11 new SHA-unique logs staged in:

- `data/to_label/2026-02-23_batch/`

Team sheets are prepared:

- `data/to_label/2026-02-23_batch/label_assignment.csv`
- `data/to_label/2026-02-23_batch/label_assignment_team.csv`
- `data/to_label/2026-02-23_batch/ground_truth_draft.json`

## Target Data To Collect Externally

Minimum target: 10 unique logs per label.

- Need +10 each: `power_instability`, `motor_imbalance`, `ekf_failure`, `mechanical_failure`, `brownout`, `crash_unknown`, `healthy`
- Need +9 each: `gps_quality_poor`, `pid_tuning_issue`
- Need +6: `rc_failsafe`
- Need +5: `compass_interference`
- Need +2: `vibration_high`

## Where To Search

- discuss.ardupilot.org crash-analysis and support threads with `.bin`/`.zip` attachments
- ArduPilot GitHub issues where users attach DataFlash logs
- Community groups where pilots can share original DataFlash `.bin`

## Suggested Query Phrases

- `power_instability`: "battery sag", "voltage drop", "brownout", "reboot in air"
- `motor_imbalance`: "ESC desync", "motor mismatch", "yaw spin crash"
- `ekf_failure`: "EKF variance", "lane switch", "EKF failsafe"
- `mechanical_failure`: "broken prop", "arm crack", "mechanical vibration crash"
- `brownout`: "FC reboot", "power reset", "Pixhawk reboot"
- `crash_unknown`: "sudden crash no error"
- `gps_quality_poor`: "GPS glitch", "HDOP high", "satellites drop"
- `pid_tuning_issue`: "oscillation", "PID tuning", "D-term noise"
- `rc_failsafe`: "radio failsafe", "RC link loss", "receiver drop"

## Required Submission Fields

Each contributed log must include:

1. DataFlash `.bin` file (required)
2. `source_url` (forum/issue/thread)
3. `download_url` if available
4. One label from taxonomy
5. Confidence (`medium` or `high`)
6. One-line reason with evidence

## Verification Rule Before Import

Every incoming file is deduped by SHA256. If SHA already exists in the labeled pool, it is not counted as new data.
