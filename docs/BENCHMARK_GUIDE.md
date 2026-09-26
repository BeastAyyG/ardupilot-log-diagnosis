# Understanding the ArduPilot Log Diagnosis Benchmark

A plain-language guide to what this project is, the problem it solves, and how
the pieces fit together. It is written for two readers:

- **Newcomers:** start at *Core concepts* and read top to bottom.
- **Experienced users:** jump to *How the pieces fit together* and *Current status*.

> **The honest bottom line.** This project shows that, when flight-log
> diagnosis is evaluated *correctly* (grouped by incident, not by window), the
> current ML-assisted system performs **at or below chance**. The publishable
> contribution is therefore a rigorous **benchmark + evaluation-leakage study
> with a negative result** — not a working "crash predictor." Everything below
> is built to make that claim reproducible and defensible.

---

## 1. Purpose

ArduPilot writes `.BIN` flight logs. When a vehicle crashes, a human expert
often explains the cause in a forum thread ("Vibration drove the EKF insane",
"a motor desynced"). The dream is an automated tool that reads the log and
names the root cause.

The trap: it is easy to make such a tool *look* accurate by evaluating it on the
wrong split of the data. If you chop one crash into 100 windows and let 90 be
training and 10 be test, the model can memorize the *crash* instead of learning
the *cause* — and score ~0.97 F1 while being useless on a new crash. This is
**evaluation leakage**.

This project's purpose is to (a) build a benchmark that *prevents* that leakage,
(b) measure how big the leakage effect is, and (c) report the honest number.

---

## 2. Core concepts

| Term | Meaning |
|---|---|
| **Flight log** | A `.BIN` recording of one flight (sensor messages over time). |
| **Incident** | One real-world crash/failure event. The independent unit of truth. May span several log files. |
| **Root cause** | The true failure class, e.g. `ekf_failure`, `thrust_loss`, `vibration_high`. Valid only if quoted from an expert. |
| **Symptom** | What the rule engine sees (e.g. high vibration). Symptoms are *not* root causes. |
| **Window** | A slice of a log used as one ML example. Windows from one incident share the incident's label. |
| **Rule engine** | Deterministic checks (thresholds on sensor fields). Outputs symptoms. |
| **ML classifier** | A model (tree / linear) mapping log features → a root-cause probability. |
| **Hybrid fusion** | Combines the rule engine and the ML model into one answer. |
| **CITA** | *Causal Temporal Arbitration*: insists the predicted root cause's onset time is before its symptoms'. A constraint, not a feature. |
| **Onset time** | When a cause/symptom began in the log (seconds). Enables the CITA test. |
| **Leakage** | Test information leaking into training (or a split that lets the model cheat), making scores too good. |
| **Split family** | How data is divided for train/test: *random windows* (leaky), *by log*, or *by incident* (honest). |
| **Macro-F1** | Average F1 across classes; the headline accuracy metric. |
| **ECE** | Expected Calibration Error: do confidence scores match reality? |
| **Confirmatory holdout** | A fresh set of incidents scored *only* on frozen models — no tuning allowed. |
| **Evidence ledger** | A file where every published number must live with the one command that reproduces it. |
| **Pre-registration** | Writing the hypotheses and method *before* seeing the holdout results. |

---

## 3. Key components

### 3.1 The diagnosis pipeline

```
   log features ──► [ ML classifier ] ──┐
                                       ├──► [ Hybrid fusion ] ──► answer
   log ───────────► [ Rule engine ] ───┘        (CITA orders onsets)
```

- The **rule engine** names symptoms reliably but rarely the true cause.
- The **ML classifier** learns from features but, grouped by incident, does not
  beat chance.
- **CITA** re-orders predictions in time; it cannot fix a misidentified cause.

### 3.2 The benchmark dataset (versions)

| Version | What it is | Status |
|---|---|---|
| v1 | 37 incidents, provisional labels | Superseded (leakage) |
| v2 | 22 logs, thread-verified labels, κ=0.39 vs old | Reproducible |
| v3 | 34 logs / 32 incidents, AI-annotated, pre-registered | **Primary reproducible benchmark** |
| v4 | ≥100 incidents, human spot-checked, confirmatory holdout | *Toolchain built; labels pending (maintainer)* |

### 3.3 The evaluation protocol (the anti-leakage core)

Three split families, reported together so the leakage is *visible*:

1. **Random windows** — windows shuffled ignoring incidents. *Inflated, do not trust.*
2. **By log file** — tighter.
3. **By incident** — all windows of a crash on one side. *This is the honest number.*

### 3.4 The toolchain (scripts)

| Script / file | What it does |
|---|---|
| `src/data/expert_label_miner.py` | Finds forum crash threads with `.bin` attachments. |
| `training/fetch_adaptation_pool.py` | Downloads + SHA256-hashes logs. |
| `training/verify_thread_annotations.py` | Checks each label cites a real expert quote. |
| `training/build_benchmark_v4.py` | Assembles `ground_truth_real_v4.json`; **exits 2 if labels are missing (no fabrication)**. |
| `training/propose_onsets.py` | Proposes onset times from domain thresholds + plots. |
| `training/baselines/` | LogAnalyzer and LLM baselines for comparison. |
| `training/paper_eval.py` | Runs the full eval, records commit + hashes + seeds, writes a ledger. |
| `docs/PREREGISTRATION_V4.md` | Freezes models/metrics; states the hypotheses before scoring. |
| `docs/EVIDENCE_LEDGER.md` | Every published number + its reproduction command. |
| `docs/PUBLICATION_PLAN.md` | The remaining steps to a publishable result. |

---

## 4. How the pieces fit together

```
 forum thread + .bin log
        │
        ▼
 [ label miner ] ──────► thread_annotations_v4.json   (expert quote per label)
        │                        │
        ▼                        ▼
 [ fetch + hash ]        [ build_benchmark_v4 ]
        │                        │
        ▼                        ▼
 data/raw/...  ───────►  ground_truth_real_v4.json
                               │
            ┌──────────────────┼──────────────────┐
            ▼                  ▼                  ▼
     [ propose_onsets ]   [ paper_eval ]     [ baselines ]
            │                  │                  │
            ▼                  ▼                  ▼
      onset_time_s       H1–H4 verdicts     LogAnalyzer / LLM
            │                  │
            └────────►  EVIDENCE_LEDGER  ◄── PREREGISTRATION_V4 (frozen)
                               │
                               ▼
                   paper/  +  Zenodo DOI  +  arXiv
```

**Narrative.** A forum thread with a crash log becomes a *label* (quoted from the
expert). Logs are hashed so results are reproducible. `build_benchmark_v4.py`
turns labels + v3 into a clean ground truth. `propose_onsets.py` adds onset
times so CITA can be tested. `paper_eval.py` scores the system under the three
splits and records everything; the verdicts land in the evidence ledger, gated by
the pre-registration. Finally the paper + DOI + preprint make it citable.

---

## 5. Worked examples

**Example A — an onset proposal.** On `sample.bin`, the vibration channel
`VIBE.VibeZ` climbs to 32.48 and crosses the domain threshold of 30.0 at
`t = 215.17 s`. `propose_onsets.py` returns that as the proposed onset; a human
opens the saved plot and confirms or rejects it. That confirmed time is what
makes the CITA / onset-ordering test meaningful.

**Example B — the leakage staircase (v3, real numbers).**

| Split | RandomForest F1 |
|---|---|
| Random windows (leaky) | 0.971 |
| By log file | 0.088 |
| By incident (honest) | **0.056 ± 0.009** |
| Chance (freq-random) | 0.076 |

The ~10× drop from random-window to incident-grouped *is* the leakage effect.
The honest number (0.056) is **at or below chance (0.076)** — so the system does
not beat chance. That is the finding.

**Example C — CITA does not rescue it.** In v3, hybrid fusion with CITA *off*
got 3/34 correct; with CITA *on* it got **0/34** (CITA merely re-ordered wrong
answers). Hence CITA is reported as not helping (hypothesis H3).

---

## 6. Current status (honest)

- **Reproducible (v3):** tree models 0.056–0.069 incident-grouped F1; chance
  0.076; leakage 0.89–0.97 under random windows; CITA 3/34 → 0/34.
- **Toolchain for v4 is built and tested** (14 passing tests): builder, onset
  proposer, baselines, pre-registration, evidence ledger wiring.
- **Still needed (maintainer-only external work):** ≥100 human-reviewed incident
  labels, ~30 confirmed onsets, the confirmatory v4 run, the 10–14 page paper,
  Zenodo DOI, arXiv preprint, journal submission. See `docs/PUBLICATION_PLAN.md`.

---

## 7. Further reading

- `docs/EVIDENCE_LEDGER.md` — every number and its reproduction command.
- `docs/PREREGISTRATION_V4.md` — the frozen protocol and hypotheses H1–H4.
- `docs/PUBLICATION_PLAN.md` — the step-by-step path to publication.
- `CORRECTIONS.md` — what was retracted and why (keeps the honesty trail).
