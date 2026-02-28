# ArduPilot AI Log Diagnosis — Strategic Upgrade Roadmap

**Mission**: Become the definitive flight-log diagnostic tool for the ArduPilot ecosystem —
faster triage, higher accuracy, honest confidence, zero guesswork for maintainers.

**Current state (v1.0.0, 2026-02-28)**: Hybrid rule + XGBoost engine. 242× triage speedup.
90% compass recall, 85% vibration recall. 0 runtime crashes. 56 tests passing.

**This document**: An ordered, executable upgrade plan to reach v2.0.0 production quality —
the standard required to be the best open-source flight diagnostic tool ever built.

---

## Why This Order

The failure modes that are still weak (motor imbalance F1=0.15, power F1=0.00, rc_failsafe F1=0.29)
share a root cause: **label quality, not rule logic**. The `gsoc_attack_plan.md` correctly
identifies that the current training data mixes root-cause and symptom labels. Fixing data quality
first (Phase 1) multiplies the value of everything that follows it, because you are training
and evaluating on truth instead of noise.

---

## Phase 1 — Label Quality & ML Retraining
**Target**: Motor imbalance F1 > 0.60, power/rc_failsafe F1 > 0.50. Overall Macro F1 > 0.55.

### U-01: SMOTE + Class Balancing for Rare Labels

**Problem**: The training set has 1 `gps_quality_poor` example and 2 `pid_tuning_issue` examples.
XGBoost cannot learn from 1–2 samples. It predicts the common classes even when a rare one is correct.

**Solution**: Add `imbalanced-learn` SMOTE to `training/train_model.py`.
Switch from `OneVsRest` multi-label to strict `multiclass` since Root-Cause Precedence
guarantees exactly one root cause per log.

```python
# In training/train_model.py
from imblearn.over_sampling import SMOTE
from sklearn.preprocessing import LabelEncoder

sm = SMOTE(random_state=42, k_neighbors=min(5, min_class_size - 1))
X_resampled, y_resampled = sm.fit_resample(X_train, y_train_encoded)
```

**Files**: `training/train_model.py`
**Test**: `pytest tests/test_ml_classifier.py` — verify balanced class distribution in resampled set.

---

### U-02: GridSearchCV Hyperparameter Tuning

**Problem**: The current XGBoost model uses default parameters. `max_depth=6`, `learning_rate=0.3` 
are rarely optimal for a 60-feature, 8-class diagnostic problem.

**Solution**: Add `GridSearchCV` or `Optuna` sweep in `training/train_model.py`.

```python
param_grid = {
    "max_depth": [3, 4, 5, 6],
    "learning_rate": [0.05, 0.1, 0.2],
    "n_estimators": [100, 200, 300],
    "scale_pos_weight": [1, 2, 5],   # handles remaining class imbalance
    "min_child_weight": [1, 3, 5],
}
```

**Files**: `training/train_model.py`
**Effort**: Low — one afternoon. High reward.

---

### U-03: Confidence Calibration (ECE ≤ 0.08)

**Problem**: ECE is currently unmeasured. A model that outputs "95% confidence" on a wrong
prediction is worse than a model that outputs "65% confidence" — it destroys user trust.

**Solution**: Wrap the XGBoost classifier with `sklearn.calibration.CalibratedClassifierCV`
using isotonic regression. Add an ECE measurement script.

```python
from sklearn.calibration import CalibratedClassifierCV
calibrated_clf = CalibratedClassifierCV(xgb_clf, method="isotonic", cv=5)
calibrated_clf.fit(X_train, y_train)
```

Add `training/measure_ece.py` that loads the holdout predictions and computes per-class
Expected Calibration Error, reporting pass/fail against the ≤ 0.08 target.

**Files**: `training/train_model.py`, new `training/measure_ece.py`
**Hard Gate**: ECE ≤ 0.08 before claiming production confidence is trustworthy.

---

### U-04: `tanomaly` Feature Coverage for All 8 Labels

**Problem**: The Temporal Arbiter in `hybrid_engine.py` only has `prefix_map` entries for 6 of
8 labels. `rc_failsafe` and `pid_tuning_issue` have no `tanomaly` key, so the arbiter never
fires for them — they can only win via confidence score, not timing evidence.

**Solution**: Add `rc_failsafe_tanomaly` and `pid_tuning_tanomaly` extraction in the feature
pipeline, and add them to `prefix_map` in `hybrid_engine.py`.

```python
# In hybrid_engine.py — prefix_map
"rc_failsafe":     "rc_failsafe",   # maps to rc_failsafe_tanomaly in features
"pid_tuning_issue": "pid_sat",       # maps to pid_sat_tanomaly in features
```

**Files**: `src/features/` (extractor), `src/diagnosis/hybrid_engine.py`
**Test**: Add `test_temporal_arbiter_rc_failsafe()` in `tests/test_diagnosis.py`.

---

## Phase 2 — False-Critical Rate Audit & Abstention
**Target**: FCR ≤ 10%. Abstention on genuinely ambiguous/corrupted logs.

### U-05: False Critical Rate Measurement Script

**Problem**: FCR is currently `TBD` in `AGENTS.md`. You cannot improve a metric you cannot measure.

**Solution**: Create `training/measure_fcr.py`. It takes a "healthy flight reference set"
(logs explicitly verified as healthy by the rule engine under all thresholds), runs the
hybrid engine over them, and counts any diagnosis with `severity == "critical"` as a
false critical. Outputs a pass/fail against the ≤ 10% target.

**Files**: New `training/measure_fcr.py`
**Integration**: Add step to CI once a reference "healthy" holdout subset is curated.

---

### U-06: Abstention / Human-Review State

**Problem**: The engine currently always outputs a diagnosis. If the log is corrupted or the 
confidence is marginal on an ambiguous failure, outputting a wrong confident answer is worse
than saying "I don't know — send to a human."

**Solution**: Add a formal `UNCERTAIN_ABSTAIN` state to the decision policy.

```python
# In src/diagnosis/decision_policy.py
MAX_ABSTAIN_CONFIDENCE = 0.50  # anything below this with no rule evidence = abstain

if top_conf < MAX_ABSTAIN_CONFIDENCE and not any_rule_fired:
    return {
        "decision": "uncertain",
        "reason_code": "low_confidence_abstain",
        "recommendation": "Confidence below threshold. Manual review recommended.",
        "diagnoses": []
    }
```

**Files**: `src/diagnosis/decision_policy.py`, `src/cli/formatter.py`
**Test**: Add `test_abstention_on_empty_features()` in `tests/test_diagnosis.py`.

---

## Phase 3 — Similar-Case Retrieval Engine (GSoC T8)
**Target**: Working retrieval for top-3 similar forum cases. This is the most user-facing
feature beyond the diagnosis itself.

### U-07: Retrieval Engine Activation

**Problem**: The retrieval engine (`src/retrieval/`) is scaffolded but currently not wired
into the CLI output. Users get a diagnosis but no "here's a forum thread with the same crash."
This is the most immediately useful feature for maintainers triaging user reports.

**Solution**:
1. Curate a feature-vector index from the 44 benchmark logs (already have features).
2. Wire `src/retrieval/case_retriever.py` into `src/cli/main.py` `analyze` command.
3. Output top-3 similar cases (forum thread URL + similarity score + their diagnosis label)
   at the bottom of every report.

```bash
# Target CLI output
Similar cases from ArduPilot forum:
  [1] 94.2% match — vibration_high — https://discuss.ardupilot.org/t/.../56863
  [2] 87.1% match — vibration_high — https://discuss.ardupilot.org/t/.../71234
  [3] 79.4% match — compass_interference — https://discuss.ardupilot.org/t/.../88901
```

**Files**: `src/retrieval/case_retriever.py`, `src/cli/main.py`, `src/cli/formatter.py`

---

## Phase 4 — Data Expansion & Label Coverage
**Target**: All 8 labels have ≥ 5 examples in the training set and holdout set.

### U-08: Expand `gps_quality_poor` and `pid_tuning_issue` Training Data

**Problem**: Current splits: 1 GPS example, 2 PID examples. These are mathematically impossible
to train or evaluate meaningfully. The label simply needs more data.

**Solution**:
1. Run `mine-expert-labels` with a query set focused on GPS/PID topics.
2. Target 10+ verified examples per label before running the next retraining cycle.
3. Update `docs/root_cause_policy.md` with clear telemetry signatures for these two labels
   so future labelers know what to look for.

**Files**: New `ops/expert_label_pipeline/queries/gps_pid_expansion.json`

---

### U-09: Batch Triage Mode

**Problem**: Maintainers receive multiple logs per forum thread. The CLI only handles one file
at a time. Running 20 logs individually is friction.

**Solution**: Add `python -m src.cli.main batch-analyze` that accepts a directory and outputs:
- A summary CSV with `filename, top_diagnosis, confidence, severity`
- Individual JSON reports per log
- A terminal summary table

```bash
python -m src.cli.main batch-analyze ./crash_logs/ --output-dir ./reports/
```

**Files**: `src/cli/main.py`, new command handler
**Effort**: Medium — reuses existing `analyze` pipeline, adds loop + CSV writer.

---

## Phase 5 — Observability & Reproducibility (GSoC Final Deliverable)
**Target**: Any reviewer can reproduce the final benchmark from a clean environment in one command.

### U-10: Model Card (`docs/model_card.md`)

The GSoC final submission requires a model card. This documents:
- What the model can and cannot detect
- Training data provenance (SHA-verified, expert-labeled, zero-leakage)
- Per-class performance with honest limitations
- Known failure modes (e.g., GPS/PID still undertrained)
- How to retrain from scratch

**Files**: New `docs/model_card.md`

---

### U-11: One-Command Reproducibility Script

```bash
# Anyone can run this on a clean clone to reproduce the final benchmark
python training/reproduce_benchmark.py --from-scratch
```

This script: cleans artifacts, rebuilds dataset, retrains model, runs benchmark, prints report.
It is the single most important thing for GSoC mentor credibility.

**Files**: New `training/reproduce_benchmark.py`

---

### U-12: Weekly Regression Benchmark via CI

**Problem**: There is no automated check that a code change hasn't degraded benchmark performance.
A regression that drops vibration recall from 85% to 60% would be invisible until noticed manually.

**Solution**: Store baseline benchmark JSON in the repo. CI job runs `benchmark --engine hybrid`
against the frozen 10-log pilot set and fails if any metric degrades below baseline.

```yaml
# In ci.yml — add:
- name: Regression benchmark
  run: python -m src.cli.main benchmark --engine hybrid --assert-min-f1 0.55
```

**Files**: `.github/workflows/ci.yml`, `src/cli/main.py` (add `--assert-min-f1` flag)

---

## Priority Order (Recommended Execution Sequence)

| # | Upgrade | Impact | Effort | Phase |
|---|---------|--------|--------|-------|
| U-01 | SMOTE + multiclass switch | 🔴 Critical | Low | 1 |
| U-02 | Hyperparameter tuning | 🔴 Critical | Low | 1 |
| U-03 | Confidence calibration (ECE) | 🔴 Critical | Medium | 1 |
| U-04 | tanomaly coverage for all 8 labels | 🟠 High | Low | 1 |
| U-05 | FCR measurement script | 🟠 High | Low | 2 |
| U-06 | Abstention state | 🟠 High | Medium | 2 |
| U-07 | Retrieval engine activation | 🟠 High | Medium | 3 |
| U-08 | Data expansion (GPS/PID) | 🟠 High | High | 4 |
| U-09 | Batch triage mode | 🟡 Medium | Medium | 4 |
| U-10 | Model card | 🟡 Medium | Low | 5 |
| U-11 | One-command reproducibility | 🔴 Critical | Low | 5 |
| U-12 | CI regression benchmark | 🟡 Medium | Low | 5 |

---

## What "Best In Class" Looks Like

When all phases complete, this tool will be:

1. **The most honest flight diagnostic tool** — calibrated confidence, formal abstention, never
   invents a root cause it cannot support with evidence.
2. **The fastest** — 242× already proven. Batch mode extends this to unlimited scale.
3. **The most explainable** — every diagnosis carries exact `feature → value → threshold → context`
   evidence chains and actionable recommendations.
4. **Reproducible from any clean environment** — one-command benchmark reproduction, model card,
   SHA-verified provenance on all training data.
5. **The only tool** that distinguishes root cause from symptom cascade at the telemetry level —
   not just printing "EKF failure" when vibration was the actual culprit.

That is a genuinely novel contribution to ArduPilot. No other tool does all five.
