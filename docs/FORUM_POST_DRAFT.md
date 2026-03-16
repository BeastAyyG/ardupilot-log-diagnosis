# ArduPilot AI Log Diagnosis — GSoC 2026 Pre-Application Introduction

**Category:** GSoC 2026 / Development Tools
**Post to:** https://discuss.ardupilot.org/c/gsoc/37

---

Hi everyone,

I'm Agastya Pandey, a B.Tech student (AI & ML) at SRM University AP. I'm applying for GSoC 2026 with a project focused on **automated crash log diagnosis** for ArduPilot.

## What I've Built

I've developed a working prototype of an AI-powered `.BIN` flight log diagnostic tool:

**Repository:** [BeastAyyG/ardupilot-log-diagnosis](https://github.com/BeastAyyG/ardupilot-log-diagnosis)

The tool takes a dataflash `.BIN` file and produces:
- **Root-cause identification** (not just anomaly flags)
- **Evidence** tied to exact feature values and thresholds
- **Actionable recommendations** (ranked fixes and next steps)
- **Confidence-calibrated output** with mandatory abstention for uncertain cases

### Architecture
```
.BIN → Parser (pymavlink) → 60+ Feature Extractors → Rule Engine → XGBoost ML → Hybrid Fusion → Causal Arbitration → Report
```

### Current Capabilities
- **Physics-based rule engine** covering vibration, compass, EKF, GPS, motors, power, RC failsafe, PID tuning, and mechanical failure
- **Temporal causal arbiter** — detects that if vibration started 30s before an EKF failure, vibration is the *root cause*, not the symptom
- **162 passing tests**, full CI, SHA256-verified data provenance
- CLI: `python -m src.cli.main analyze flight.BIN`

### Honest Benchmark Results (45 real crash logs)
| Label | N | TP | F1 |
|---|---|---|---|
| vibration_high | 10 | 3 | 0.40 |
| compass_interference | 12 | 3 | 0.25 |
| ekf_failure | 4 | 3 | 0.38 |
| motor_imbalance | 7 | 3 | 0.21 |
| power_instability | 5 | 0 | 0.00 |
| rc_failsafe | 3 | 0 | 0.00 |
| pid_tuning_issue | 2 | 0 | 0.00 |

**Overall Macro F1: 0.14** — honest and low. This is a rule-only engine without ML model weights (the XGBoost model is experimental and needs more labeled data).

## GSoC Plan

The core work for GSoC would be:
1. **Expand the labeled dataset** from 45 to 500+ logs using the expert label mining pipeline
2. **Improve weak failure categories** (motor_imbalance, power_instability, PID, RC failsafe)
3. **Train and validate the ML classifier** with enough data to meaningfully outperform rule-only
4. **Triage time validation** with real ArduPilot maintainers

## What I'd Love from This Community

- **Feedback on the diagnostic output format** — is this useful for triage?
- **Crash logs you'd be willing to share** for the training dataset (I document full provenance for every log)
- **Review of the rule engine thresholds** — are they sensible for real-world ArduPilot behavior?

I've read the ArduPilot GSoC guidelines and I'm looking for a mentor who works with flight log analysis. Happy to answer any questions about the architecture or share a demo.

Thanks for reading!
— Agastya
