# Labeling Sprint - 2026-02-23 Batch

- Total logs: **11**
- Files: `*.bin` in this folder
- Assignment sheet: `label_assignment.csv`
- Team assignment: `label_assignment_team.csv` and `TEAM_SPLIT.md`
- Fill labels in: `ground_truth.json`

## Suggested Primary Label Mix (from heuristic cues)
- compass_interference: 1
- ekf_failure: 1
- motor_imbalance: 6
- power_instability: 3

## How to Label
1. Open each `.bin` in Mission Planner DataFlash review.
2. Confirm root-cause label (not every symptom).
3. Fill `ground_truth.json` fields: `label`, `confidence`, `reason`.
4. Keep `reason` to one concrete line with metric evidence.

## Priority
- Start with rows marked `P0` in `label_assignment.csv`.
- Try to maximize missing classes: power/motor/EKF/mechanical/brownout/crash/rc failsafe.
