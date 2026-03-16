# 🚁 ArduPilot AI Log Diagnosis — Forum Announcement

> **Thread title:** [Tool] AI-powered `.BIN` log diagnostic analyzer — 84% faster triage, evidence-based root-cause output

---

## What this is

A command-line tool that accepts any ArduPilot `.BIN` dataflash log and, in under
3 seconds, returns an **evidence-based root-cause diagnosis** with:

- **Root cause label** (vibration, compass EMI, EKF failure, power sag, motor
  imbalance, RC failsafe, PID tuning, thrust loss, mechanical failure, …)
- **Exact feature values that fired** (e.g. `vibe_z_max = 67.8`, limit 30.0)
- **Confidence percentage** calibrated against 45 real crash logs
- **Fix recommendation** ("Balance or replace propellers. Check motor mount tightness.")
- **Subsystem blame ranking** (which subsystem is most likely responsible)
- **Similar historical cases** (cosine-similarity search against a curated knowledge base)
- **Human-review flag** raised automatically when confidence is below threshold

The engine is a hybrid of an **evidence-driven rule engine** (threshold-matched
against ArduPilot internals) and a trained **XGBoost classifier** (60+ features
extracted per log).

---

## Quick demo (no `.BIN` needed)

```bash
git clone https://github.com/BeastAyyG/ardupilot-log-diagnosis
cd ardupilot-log-diagnosis
pip install -r requirements.txt
python -m src.cli.main demo
```

Sample output:

```
╔═══════════════════════════════════════╗
║  ArduPilot Log Diagnosis Report       ║
╠═══════════════════════════════════════╣
║  Log:      demo_flight.BIN            ║
║  Duration: 5m 42s                     ║
║  Vehicle:  ArduCopter 4.5.1           ║
╚═══════════════════════════════════════╝

CRITICAL — VIBRATION_HIGH (95%)
  vibe_z_max = 67.8 (limit: 30.0)
  vibe_clip_total = 145 (limit: 0)
  Method: rule+ml
  ➜ Fix: Balance or replace propellers. Check motor mount tightness.

WARNING — EKF_FAILURE (72%)
  ekf_vel_var_max = 1.8 (limit: 1.5)
  ekf_lane_switch_count = 2 (limit: 0)
  Method: rule
  ➜ Fix: Vibration is likely shaking sensors and causing cascading EKF failure.

Overall: NOT SAFE TO FLY ✘

Subsystem Blame Ranking:
  -  Vibration/Mounts: 71%
  -   Navigation/EKF: 29%

Similar Historical Cases:
  [91%] vibration_high
         Cause: Bent propeller blade after previous hard landing.
         Fix:   Replace all propellers; re-balance motors.
         Ref:   https://discuss.ardupilot.org/t/example-vibration-crash/12345
```

On a real log:

```bash
python -m src.cli.main analyze my_crash.BIN
python -m src.cli.main analyze my_crash.BIN --format html -o report.html
```

---

## Why this might be useful for the community

**Current maintainer workflow:**

1. Download `.BIN` from forum post
2. Open in Mission Planner / MAVExplorer
3. Manually scan vibration, EKF, GPS, battery, motor channels
4. Cross-reference docs / similar reports
5. Post diagnosis — often **8+ minutes** per log

**With this tool:**

```
$ time python -m src.cli.main analyze crash.BIN
… (diagnosis output) …
real    0m2.1s
```

Benchmark results on **45 real crash logs** sourced from `discuss.ardupilot.org`
with expert-verified ground-truth labels:

| Metric                    | Result    |
|---------------------------|-----------|
| Compass Interference Recall | **90%**  |
| Vibration Cascade Recall    | **85%**  |
| EKF Failure F1              | **0.67** |
| Triage time reduction       | **84%** (4 mins vs 25 mins) |
| Parse reliability           | **97.8%** (44/45 logs extracted) |

---

## Output formats

| Format     | Command                                         | Use case           |
|------------|-------------------------------------------------|--------------------|
| Terminal   | `python -m src.cli.main analyze flight.BIN`     | Quick triage       |
| JSON       | `… --format json`                               | Automation / CI    |
| **HTML**   | `… --format html -o report.html`               | Forum attachments, sharing |

---

## Current limitations (honest)

- **Motor imbalance / PID** rules are still being tuned — improvements in progress
- **Multi-label** precision dips in cascading failure cases (vibration → compass → EKF)
- ML model was trained on a relatively small dataset (45 labeled logs); improving with
  the expert-label miner pipeline

---

## This is a GSoC 2026 project proposal

The goal is to build this into a production-quality tool during GSoC, with:
- Larger, community-sourced training dataset
- Improved per-label coverage (especially motor imbalance, power, PID)
- ArduPilot integration (optional Mission Planner plugin)
- Community contribution workflow for new crash log labels

See the full proposal: [`docs/GSOC_PROPOSAL.md`](GSOC_PROPOSAL.md)

---

## Links

- GitHub: <https://github.com/BeastAyyG/ardupilot-log-diagnosis>
- Benchmark results: [`benchmark_results.md`](../benchmark_results.md)
- Triage study: [`docs/MAINTAINER_TRIAGE_REDUX.md`](MAINTAINER_TRIAGE_REDUX.md)
- Contributing crash logs: [`CONTRIBUTING.md`](../CONTRIBUTING.md)

Feedback welcome — especially from developers who review crash logs regularly.
