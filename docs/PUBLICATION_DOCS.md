# ArduPilot Log Diagnosis — Publication Documentation

**One combined document for the publication track.** It merges the benchmark
guide, the publication plan, and the remaining-work status into a single read.
It is written so that a newcomer (developer or stakeholder) can understand what
the project is, what it has proven, and exactly what is left to do.

**Contents**
1. Purpose and honest bottom line
2. Core concepts (glossary)
3. Key components and how they fit together
4. Worked examples
5. The publication plan (Steps 1, 2, 3, 5, 6)
6. Remaining work (status of every task)
7. Cross-cutting notes, decisions, and out-of-scope tracks
8. Further reading

---

## 1. Purpose and honest bottom line

ArduPilot writes `.BIN` flight logs. When a vehicle crashes, a human expert often
explains the cause in a forum thread ("Vibration drove the EKF insane", "a motor
desynced"). This project diagnoses those logs automatically, combining a
deterministic **rule engine**, a **machine-learning classifier**, and a temporal
fusion layer called **CITA**.

The trap: a diagnosis system can *look* accurate if it is evaluated on the wrong
split. Divide one crash into 100 windows and let 90 train / 10 test, and the model
can memorize the *crash* rather than learn the *cause* — scoring ~0.97 F1 while
being useless on a new crash. That failure mode is **evaluation leakage**.

> **The honest bottom line.** Evaluated correctly (grouped by incident, not by
> window), the current ML-assisted system performs **at or below chance**. The
> defensible, publishable contribution is therefore a rigorous **benchmark plus an
> evaluation-leakage study, reported as a negative result** — not a working crash
> predictor. Everything below exists to make that claim reproducible.

---

## 2. Core concepts (glossary)

| Term | Meaning |
|---|---|
| **Flight log** | A `.BIN` recording of one flight (sensor messages over time). |
| **Incident** | One real-world crash/failure event. The independent unit of truth. May span several log files. |
| **Root cause** | The true failure class, e.g. `ekf_failure`, `thrust_loss`, `vibration_high`. Valid only if quoted from an expert. |
| **Symptom** | What the rule engine sees (e.g. high vibration). Symptoms are *not* root causes. |
| **Window** | A slice of a log used as one ML example. Windows from one incident share its label. |
| **Rule engine** | Deterministic threshold checks on sensor fields. Outputs symptoms. |
| **ML classifier** | A model (tree / linear) mapping log features → a root-cause probability. |
| **Hybrid fusion** | Combines the rule engine and the ML model into one answer. |
| **CITA** | *Causal Temporal Arbitration*: insists the predicted root cause's onset time precedes its symptoms'. A constraint, not a feature. |
| **Onset time** | When a cause/symptom began in the log (seconds). Enables the CITA test. |
| **Leakage** | Test information leaking into training (or a split that lets the model cheat), making scores too good. |
| **Split family** | How data is divided: *random windows* (leaky), *by log*, or *by incident* (honest). |
| **Macro-F1** | Average F1 across classes; the headline accuracy metric. |
| **ECE** | Expected Calibration Error: do confidence scores match reality? |
| **Confirmatory holdout** | A fresh set of incidents scored *only* on frozen models — no tuning allowed. |
| **Evidence ledger** | A file where every published number must live with the one command that reproduces it. |
| **Pre-registration** | Writing the hypotheses and method *before* seeing the holdout results. |

---

## 3. Key components and how they fit together

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
| `docs/PREREGISTRATION_V4.md` | Freezes models/metrics; states hypotheses before scoring. |
| `docs/EVIDENCE_LEDGER.md` | Every published number + its reproduction command. |
| `docs/PUBLICATION_PLAN.md` | The remaining steps to a publishable result. |

### 3.5 End-to-end data flow

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

A forum thread with a crash log becomes a *label* (quoted from the expert). Logs
are hashed so results are reproducible. `build_benchmark_v4.py` turns labels + v3
into a clean ground truth. `propose_onsets.py` adds onset times so CITA can be
tested. `paper_eval.py` scores the system under the three splits and records
everything; the verdicts land in the evidence ledger, gated by the
pre-registration. Finally the paper + DOI + preprint make it citable.

---

## 4. Worked examples

**Example A — an onset proposal.** On `sample.bin`, the vibration channel
`VIBE.VibeZ` climbs to 32.48 and crosses the domain threshold of 30.0 at
`t = 215.17 s`. `propose_onsets.py` returns that as the proposed onset; a human
opens the saved plot and confirms or rejects it. That confirmed time is what makes
the CITA / onset-ordering test meaningful.

**Example B — the leakage staircase (v3, real numbers).**

| Split | RandomForest F1 |
|---|---|
| Random windows (leaky) | 0.971 |
| By log file | 0.088 |
| By incident (honest) | **0.056 ± 0.009** |
| Chance (freq-random) | 0.076 |

The ~10× drop from random-window to incident-grouped *is* the leakage effect. The
honest number (0.056) is **at or below chance (0.076)** — so the system does not
beat chance. That is the finding.

**Example C — CITA does not rescue it.** In v3, hybrid fusion with CITA *off* got
3/34 correct; with CITA *on* it got **0/34** (CITA merely re-ordered wrong answers).
Hence CITA is reported as not helping (hypothesis H3).

---

## 5. The publication plan

**Goal:** a reproducible, incident-level benchmark for ArduPilot crash root-cause
diagnosis, paired with a controlled study of how evaluation leakage inflates
reported accuracy.

**Principles:**
- Every published number lives in `docs/EVIDENCE_LEDGER.md`.
- Every retracted number stays explained in `CORRECTIONS.md`.
- No label, onset, or metric is fabricated.

**Reproducible v3 results (the primary evidence):**

| Claim | Value |
|---|---|
| Chance: majority class / frequency-random | 0.038 / mean 0.076 |
| RandomForest: random windows → by log → by incident | 0.971 → 0.088 → **0.056 ± 0.009** |
| ExtraTrees: random windows → by log → by incident | 0.971 → 0.074 → **0.069 ± 0.002** |
| Rule engine alone | 0.062 (4/34 correct) |
| Rules + fusion, CITA off / on | 0.054 (3/34) / 0.000 (0/34) |

**Pre-registered hypotheses (v3 supported):**
- **H1 (leakage):** leakage inflates scores under random splits — supported.
- **H2 (no method beats chance):** supported.
- **H3 (CITA does not help):** supported (3/34 → 0/34).
- **H4 (v4 replicates v3):** to be tested on the confirmatory holdout.

**The remaining steps** (detail in Section 6):
- **Step 1 (Task E).** arXiv preprint + Zenodo DOI.
- **Step 2 (Task A).** ≥100 real, expert-quoted incidents; human spot-check + kappa.
- **Step 3 (Task B).** Confirm ~30 onset proposals.
- **Step 5 (Tasks C+D).** Confirmatory v4 evaluation + expand the paper to 10–14 pages.
- **Step 6 (Task F).** Journal submission.

**Dependency order:**
```
A (Step 2) ──► B (Step 3) ──► C (Step 5 eval) ──► D (Step 5 paper) ──► F (Step 6)
                │                            │                         ▲
                └────────────────────────────┘                         │
E (Step 1) needs the A bundle; its DOI must land in D's Availability. ──┘
```
Task A is the critical path — B, C, and D all depend on its
`ground_truth_real_v4.json`.

---

## 6. Remaining work — status of every task

**Status badges:** `[BUILT]` (code ready), `[PENDING]` (not started, waiting on
input), `[BLOCKED]` (cannot proceed until a dependency lands), `[MAINTAINER-ONLY]`
(requires the project owner's accounts/access).

### 6.1 At a glance

| Task | Step | Owner | Status | Hard blocker |
|---|---|---|---|---|
| A | 2 — real forum labels + gate + kappa | Maintainer + human reviewer | `[PENDING]` | Forum access + human review |
| B | 3 — confirm ~30 onset proposals | Maintainer | `[BLOCKED]` | Task A (`ground_truth_real_v4.json`) |
| C | 5 — confirmatory v4 evaluation | Maintainer (runs tooling) | `[BLOCKED]` | Tasks A + B |
| D | 5 — expand paper to 10–14 pp | Maintainer (author) | `[PENDING]` | Task C results; Task E DOI |
| E | 1 — arXiv preprint + Zenodo DOI | Maintainer (external accounts) | `[PENDING]` | Task A release bundle |
| F | 6 — journal submission | Maintainer (external accounts) | `[BLOCKED]` | Tasks D + E |

**Bottom line:** no task is actively running. The engineering is done; the
bottleneck is maintainer time and external accounts, not code.

### 6.2 Task A — Step 2: real forum labels + ≥100-incident gate + human spot-check/kappa

**Goal.** Produce ≥100 real incidents whose cause is quoted from a forum expert,
human-review a random 20% (reporting Cohen's kappa), and assemble
`ground_truth_real_v4.json` — the input every later task needs.

**Status.** `[PENDING]` — not started.

**Completed so far.**
- `expert_label_miner.py` finds crash threads with `.bin` attachments.
- `fetch_adaptation_pool.py` downloads + SHA256-hashes logs (reads the existing
  `data/cohorts/cohort_manifest.json`, `adaptation_pool` cohort).
- `verify_thread_annotations.py` checks each label cites a real quote + permalink
  (exit 0 on success).
- `build_benchmark_v4.py` assembles the ground truth and **exits 2 if the labels
  file is missing** — it cannot fabricate data.
- `PREREGISTRATION_V4.md` freezes the gate: ≥100 incidents, ≥5 per scored class,
  human-reviewed.

**What is happening now.** Nothing. No `thread_annotations_v4.json` exists yet;
the builder is intentionally blocked until it does.

**What can still be done.** (Maintainer + a second human reviewer.)
1. Curate a **per-class** query list — `training/queries.json` is currently a flat
   list of 6 strings, not per-class; prioritise the rare classes (`ekf_failure`,
   `gps_quality_poor`, `brownout`, `thrust_loss`, `motor_imbalance`).
2. Run the miner to pull candidate threads; **discard its regex labels**.
3. Download + hash logs via the cohort manifest.
4. Write each label with the expert's verbatim quote + post link into
   `thread_annotations_v4.json`.
5. `verify_thread_annotations.py --annotations thread_annotations_v4.json` must
   exit 0.
6. Human-check 20% randomly; compute Cohen's kappa; write `SPOT_CHECK.md` (v4) +
   record it in `EVIDENCE_LEDGER.md`.
7. `build_benchmark_v4.py` → `ground_truth_real_v4.json` (≥100 incidents, ≥5/class;
   `--allow-missing-logs` only if some logs are undownloadable).

**Done when.** ≥100 quoted incidents in `thread_annotations_v4.json`; verification
exits 0; `SPOT_CHECK.md` (v4) reports kappa; `ground_truth_real_v4.json` meets the gate.

### 6.3 Task B — Step 3: human confirmation of ~30 onset proposals

**Goal.** Confirm ~30 onset-time proposals against the real logs and record
`onset_time_s`, enabling the CITA / onset-ordering test (H3).

**Status.** `[BLOCKED]` — waits on Task A.

**Completed so far.**
- `propose_onsets.py` plots the relevant channel per label and proposes a
  threshold-crossing onset time; writes `data/benchmark/onset_proposals.json`.
- Nine labels auto-propose (`vibration_high, ekf_failure, gps_quality_poor,
  compass_interference, thrust_loss, motor_imbalance, mechanical_failure,
  power_instability, brownout`); four (`rc_failsafe, pid_tuning_issue,
  setup_error, crash_unknown`) return "no proposal" and are manual-only.

**What is happening now.** Nothing — needs `ground_truth_real_v4.json` from A.

**What can still be done.** (Maintainer.)
1. `propose_onsets.py --annotations ground_truth_real_v4.json
   --logs data/raw/benchmark_v4 --plots` → proposals + plots.
2. Inspect each plot; mark confirmed / adjusted / rejected.
3. Write `onset_time_s` into `data/benchmark/incidents.csv` and
   `ground_truth_real_v4.json`.
4. For unmapped labels, record a documented manual onset or N/A.
5. Compute onset-ordering accuracy → `EVIDENCE_LEDGER.md`.

**Done when.** ≥30 proposals inspected with saved plots; `onset_time_s` populated
for confirmed incidents; onset-ordering accuracy recorded.

### 6.4 Task C — Step 5 (eval): confirmatory v4 evaluation run

**Goal.** Run the v4 evaluation exactly as pre-registered and report every
hypothesis (H1–H4) whatever the outcome, including a negative result.

**Status.** `[BLOCKED]` — waits on Tasks A + B.

**Completed so far.**
- `paper_eval.py` runs the full eval, records git commit + data hashes + seeds,
  and writes a traceable ledger JSON.
- Baselines (LogAnalyzer, LLM) are wired in behind `--baselines-input`.
- `PREREGISTRATION_V4.md` states H1–H4, including H4 (v4 within v3's CI 0.056–0.069).

**What is happening now.** Nothing — needs the v4 ground truth and onsets.

**What can still be done.** (Maintainer runs the tooling.)
1. Confirm `PREREGISTRATION_V4.md` is committed and frozen.
2. `paper_eval.py --ground-truth ground_truth_real_v4.json
   --derived-dir data/benchmark/derived_v4 --dataset-dir data/raw/benchmark_v4
   --models RandomForest,ExtraTrees,LogisticRegression --baselines-input <dir>`
   (seeds 1,7,21,42,99; 2000-resample bootstrap, seed 20260925).
3. Mark each H supported / not-supported with the reproduced number.
4. If at chance, frame the paper as benchmark + leakage study + negative result.

**Done when.** One command regenerates all v4 tables; `EVIDENCE_LEDGER.md` gains a
"benchmark v4" section with H1–H4 verdicts and 95% CIs; no hypothesis dropped.

### 6.5 Task D — Step 5 (paper): expand to 10–14 pages

**Goal.** Turn the ~5-page draft into a real paper (related work, dataset
construction, annotation + agreement, per-class/error analysis, calibration,
threats to validity) and cite the dataset DOI.

**Status.** `[PENDING]` — authoring not started.

**Completed so far.**
- `paper/main.tex` exists (~5 pages) and builds via `python paper/make_figures.py`
  then `pdflatex` / `bibtex`.
- Author placeholder at `main.tex` line 13; Availability/DOI section at lines 266–270.
- `CITATION.cff` has real title/abstract/license/version but a placeholder
  `authors:` block and **no `doi:` field**.
- `references.bib` last checked against Crossref/arXiv on 2026-09-25 (manual).

**What is happening now.** Nothing.

**What can still be done.** (Maintainer authors; assistant builds the PDF.)
1. Add the required sections.
2. Rebuild via `make_figures.py` + `pdflatex`/`bibtex`.
3. Re-verify `references.bib` (manual, dated).
4. Fill Availability with the Zenodo DOI (from Task E).
5. State v4 labels are human spot-checked (not "verified" until `SPOT_CHECK.md` v4
   is complete).

**Done when.** `paper/main.pdf` is 10–14 pages with all sections; references
re-verified and dated; Availability cites the DOI; label status matches
`SPOT_CHECK.md` (v4).

### 6.6 Task E — Step 1: arXiv preprint + Zenodo DOI

**Goal.** Archive the benchmark release on Zenodo (minting a DOI) and post an
arXiv preprint, with real authors and the DOI cited in the paper + `CITATION.cff`.

**Status.** `[PENDING]` — `[MAINTAINER-ONLY]` (Zenodo/arXiv accounts).

**Completed so far.**
- `make_release_bundle.py --version <v>` builds
  `dist/ardupilot-log-benchmark-v<v>.zip` (includes `DATASHEET.md`, complete for v3).
- `CITATION.cff` is structured and ready for authors + DOI.

**What is happening now.** Nothing.

**What can still be done.** (Maintainer uses external accounts; assistant fills fields.)
1. Replace author placeholders in `main.tex` + `CITATION.cff` with real name /
   affiliation / email.
2. `make_release_bundle.py --version 4.0` → zip (see decision 1: 4.0 vs also a 3.0
   snapshot).
3. Connect Zenodo to GitHub, publish the release, attach the zip, mint the DOI.
4. Add `doi:` to `CITATION.cff` and cite it in Availability.
5. Post the arXiv preprint (cs.LG, cross-listed cs.RO) with the DOI in Availability.

**Done when.** Zenodo DOI minted and archived; `CITATION.cff` has real authors +
`doi:`; arXiv preprint live citing the DOI.

### 6.7 Task F — Step 6: journal submission

**Goal.** Submit the expanded paper to a dataset/benchmark venue after checking its
current quartile.

**Status.** `[BLOCKED]` — waits on Tasks D + E. `[MAINTAINER-ONLY]`.

**Completed so far.** None (no template or cover letter exists yet).

**What is happening now.** Nothing.

**What can still be done.** (Maintainer.)
1. Pick the venue (*Engineering Applications of Artificial Intelligence* or
   *Reliability Engineering & System Safety*); check the Scimago quartile on the
   submission day. Avoid *Scientific Data* (requires open raw data; log licences
   are unverified).
2. Port `paper/main.tex` to the venue template.
3. Write the cover letter.
4. Request log-owner redistribution permission.
5. Submit.

**Done when.** Manuscript submitted in the venue template with cover letter;
permission requests logged (any denial recorded as a licensing caveat).

---

## 7. Cross-cutting notes, decisions, and out-of-scope tracks

### 7.1 Open decisions to confirm
1. **Release version:** archive v4.0 (after A) vs also a v3.0 snapshot on Zenodo.
2. **Cohen's kappa:** reported honestly; no minimum score imposed (v3 was 0.39).
3. **"~30 onsets":** target may shift once the v4 label mix is known.
4. **LLM baseline API key:** `training/baselines/llm_baseline.py` reports "not run"
   without `ARDUPILOT_LLM_API_KEY`; confirm whether a key will be supplied.

### 7.2 Honesty constraints (non-negotiable)
- No fabricated labels, onsets, or metrics.
- Every published number reproducible from one command at a clean commit.
- A negative result (system at chance) is a valid, publishable outcome.

### 7.3 Out of scope (other roadmap tracks)
These are **not** part of the publication track and are untouched:
- **Milestone 2 — LLM orchestration:** planned but not built.
- **Milestone 5 — production hardening / release:** endpoint latency still exceeds
  the 500 ms gate (~2.3 s end-to-end vs ~433 ms pipeline; `hardware_report` is 71%
  of the payload).
- **Milestone 6 — community adoption:** not started.
Milestones 3 (rule split, boundary tests, dead-label coverage, scaler decision)
and 4 (bad-input handling) are already done/audited. See `docs/UPGRADE_ROADMAP.md`.

### 7.4 Recommended starting point
Start with **Task A**, sub-step 1: curate the per-class query list. Everything
downstream is blocked on `ground_truth_real_v4.json`.

---

## 8. Further reading

- `docs/PUBLICATION_PLAN.md` — the full step-by-step plan.
- `docs/BENCHMARK_GUIDE.md` — accessible introduction to the benchmark.
- `docs/REMAINING_WORK.md` — standalone remaining-work status document.
- `docs/EVIDENCE_LEDGER.md` — every number + reproduction command.
- `docs/PREREGISTRATION_V4.md` — the frozen v4 protocol + hypotheses.
- `CORRECTIONS.md` — retracted claims and why.
- `docs/UPGRADE_ROADMAP.md` — engineering roadmap (Milestones 0–6).
