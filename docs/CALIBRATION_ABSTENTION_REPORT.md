# Calibration & Abstention Report



---

## 1. Overview

This document records the calibration quality and abstention behaviour of the
ArduPilot AI Log Diagnosis hybrid engine as of the current development release.
It satisfies the requirement in `AGENTS.md` Gate E:

> *"Calibration and abstention report included."*

---

## 2. Confidence Calibration

### 2.1 Measurement method

Calibration is measured with **Expected Calibration Error (ECE)** — a scalar
that quantifies how well predicted confidence scores match empirical accuracy.

- An ECE of 0.05 means "when the engine says 70%, it is actually correct
  65–75% of the time" — well-calibrated.
- An ECE above the 0.08 release gate means confidence outputs remain advisory.

The `training/measure_ece.py` script computes ECE from the trained
calibrated XGBoost model over the saved, group-isolated holdout flight IDs.

**Production target**: ECE ≤ 0.08

### 2.2 Calibration pipeline

For the current small dataset, the classifier uses sigmoid post-hoc calibration
(`CalibratedClassifierCV(method="sigmoid")`). Calibration is fitted within the
training data; the saved outer holdout is used only for final reporting.

```
Raw XGBoost score  →  Sigmoid calibration  →  calibrated probability
```

### 2.3 Reliability diagram

A per-class reliability diagram is saved to `docs/reliability_diagram.png`
when `training/measure_ece.py` is run. The diagram plots predicted confidence
bins (x-axis) against observed accuracy (y-axis). A perfectly calibrated model
follows the diagonal.

To regenerate:

```bash
python training/measure_ece.py \
    --features-csv training/features.csv \
    --labels-csv training/labels.csv \
    --output-diagram docs/reliability_diagram.png
```

The JSON report is saved to `training/ece_report.json`.

The current saved-holdout result is **ECE 0.1268 on 22 unseen flight groups**.
This fails the ≤ 0.08 production target, so ML confidence remains advisory and
the project must not claim that the calibration gate has passed.

---

## 3. Abstention / Human-Review Policy

### 3.1 Policy definition

The `src/diagnosis/decision_policy.evaluate_decision()` function applies a
safety gate on top of the ranked diagnosis list. It returns one of three
mutually exclusive states:

| Status | `requires_human_review` | Meaning |
|---|---|---|
| `healthy` | `False` | No diagnosis produced; flight appears nominal. |
| `uncertain` | `True` | Engine is not confident enough to act autonomously — human must review. |
| `confirmed` | `False` | Top diagnosis confidence and separation pass the safety gate. |

### 3.2 Abstention triggers

A diagnosis result is escalated to `uncertain` (abstain) when **any** of the
following conditions hold:

1. **Low top confidence** — top confidence < `abstain_threshold` (default 0.65).
2. **Close top-2 gap** — difference between #1 and #2 confidence < `close_margin`
   (default 0.15); indicates ambiguity between two plausible root causes.
3. **Multiple high-confidence signals** — more than one diagnosis has confidence
   ≥ 0.5; suggests cascading failures where the true root cause is unclear.
4. **ML-only moderate prediction** — top result comes only from the ML classifier
   (not confirmed by rule engine) and confidence < 0.75.

### 3.3 Test coverage

Abstention behaviour is verified in `tests/test_hard_gates.py` (class
`TestGateE`) and `tests/test_decision_policy.py`. Key scenarios covered:

- Empty diagnosis list → `healthy`
- Low-confidence top result → `uncertain`
- Close top-2 gap → `uncertain`
- High-confidence clear winner → `confirmed`
- Output schema completeness (all required keys present)
- Rationale list is non-empty and contains human-readable strings
- Subsystem blame scores are present and ranked

---

## 4. False-Critical Rate (FCR) Audit

### 4.1 Definition

**FCR** = (number of `critical` severity diagnoses on verified-healthy logs) /
(total verified-healthy logs).

A high FCR means the tool "cries wolf" and degrades maintainer trust faster
than a high miss-rate does.

**Production target**: FCR ≤ 5%

### 4.2 Measurement script

`training/measure_fcr.py` accepts a directory of manually verified healthy
`.BIN` flight logs and outputs:

- Per-file result (clean or false-critical)
- Aggregate FCR with pass/fail against the ≤ 5% target
- JSON report at `training/fcr_report.json`

```bash
python training/measure_fcr.py --healthy-dir data/healthy_reference_set/ -v
```

### 4.3 FCR mitigation measures already in place

The following rule-engine guards reduce false-critical emissions on healthy
flights:

| Guard | Implementation |
|---|---|
| Compass suppressed during motor saturation | `_check_compass`: skipped when `motor_saturation_pct > 0.3` |
| GPS check skipped when no GPS data recorded | `_check_gps`: skipped when all GPS features are 0 |
| Motor imbalance requires both max AND mean elevated | `_check_motors`: `conf < 0.55` → skip |
| EKF failure requires 2+ variances OR lane switch | `_check_ekf`: single moderate variance alone is ignored |
| Increased motor-spread thresholds (400/200 PWM) | Prevents firing on normal hover oscillations |
| Raised compass-range threshold (600 mGauss) | Reduces false positives from normal motor EMI |

---

## 5. Summary

| Metric | Target | Status |
|---|---|---|
| ECE | ≤ 0.08 | **Fail: 0.1268 on the 22-flight saved holdout** |
| FCR | ≤ 5% | Mitigation guards in place; audited via `measure_fcr.py` |
| Abstention coverage | 100% of uncertain cases flagged | `evaluate_decision` policy enforced in all CLI and benchmark paths |
| Report availability | Gate E requirement | ✅ This document |

---

*Last updated: 2026-07-24 — calibration gate remains open.*
