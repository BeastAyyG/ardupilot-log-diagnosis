# Root-Cause Labeling Policy

**Version**: 1.0  
**Effective**: 2026-02-28  
**Status**: Active — adopted as the authoritative standard for all training data and benchmark labels in this project.

---

## Why This Policy Exists

ArduPilot crash discussions on `discuss.ardupilot.org` frequently report the **final catastrophic symptom**, not the original failure root cause. A maintainer responding to a thread may write "EKF failure" when the telemetry clearly shows vibration peaks of 80 m/s² appearing 30 seconds before EKF divergence began.

**Key finding from the Maintainer Triage Study (Feb 2026):**

> **67% of historical "Mechanical Failure" labels** in our initial dataset were telemetry-visible as `motor_imbalance` or `vibration_high` prior to impact timing. The forum label was the result symptom, and the AI tool — applying this policy — correctly re-attributes them.

Training on mislabeled symptoms causes the model to learn the wrong causal direction. This policy prevents that.

---

## The Root-Cause Precedence Policy

### Rule 1: Earliest Onset Wins
The authoritative label is the diagnosis corresponding to the **earliest anomaly detected** in the telemetry stream, defined as `tanomaly` — the timestamp of the first sample crossing a threshold.

### Rule 2: Sequential Causal Chains
If condition A physically causes condition B, the label is **A**.

| What the log shows | Correct label | Incorrect label |
|---|---|---|
| Vibration → EKF divergence | `vibration_high` | `ekf_failure` |
| Compass EMI → Yaw reset → crash | `compass_interference` | `ekf_failure` |
| Motor desync → vibration → EKF | `motor_imbalance` | `vibration_high` |
| Power sag → GPS glitch | `power_instability` | `gps_quality_poor` |

### Rule 3: Temporal Tie-Breaking
If two candidate root causes have `tanomaly` within ≤ 5 seconds of each other, the tie is broken by:
1. **Rule confidence score** (highest physical evidence wins).
2. If rule confidence is equal, **ML posterior probability** for each label takes precedence.

### Rule 4: Relabeling Obligation
All incoming labels — whether from forum expert text or maintainer annotation — **must be audited** against Rules 1–3.

If a record arrives labeled `ekf_failure` but the feature `vibe_z_max > 60` appears 30+ seconds before the first EKF variance spike, the record is relabeled `vibration_high`. This is not a correction of the original poster — it is a precision improvement for training data.

---

## Implementation in Code

The decision logic is implemented in [`src/diagnosis/decision_policy.py`](../src/diagnosis/decision_policy.py).

The relabeling pipeline for the training dataset is [`training/relabel_ground_truth.py`](../training/relabel_ground_truth.py) and [`training/relabel_holdout.py`](../training/relabel_holdout.py).

---

## Valid Labels

| Label | Trigger Subsystem |
|---|---|
| `vibration_high` | IMU vibration data (`VIBE` messages) |
| `compass_interference` | Magnetometer (`MAG` messages), field range/std |
| `ekf_failure` | EKF variance, lane switches (`NKF`/`XKF` messages) |
| `motor_imbalance` | Motor output spread, RPM asymmetry (`RCOU`, `ESC` messages) |
| `power_instability` | Battery voltage sag, current spikes (`BAT` messages) |
| `gps_quality_poor` | HDOP, satellite count, fix loss (`GPS` messages) |
| `pid_tuning_issue` | Attitude error, actuator saturation (`ATT`, `RATE` messages) |
| `rc_failsafe` | RC signal loss events (`RCIN`, `MSG` messages) |

---

## Relationship to Benchmark Integrity

The holdout set ground truth is built from labels **already audited** against this policy. Any benchmark claiming to measure root-cause accuracy must have its ground truth validated under this policy, or the comparison is invalid.
