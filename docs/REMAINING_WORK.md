# Remaining Work — Publication Track

> **Audience:** new developers and stakeholders with **no prior context**. This
> document explains exactly where the project stands and what is left to do to
> reach a publishable result.
> **Scope:** the *publication track* only — the five steps (Steps 1, 2, 3, 5, 6)
> that remain after the v4 analysis toolchain was already built. The broader
> engineering roadmap (Milestones 2, 5, 6) is noted at the end under
> *Out of scope*.

---

## 1. What this project is (plain language)

This repository diagnoses ArduPilot flight-log (`.BIN`) recordings to suggest the
**root cause** of a crash or failure (e.g. `ekf_failure`, `thrust_loss`,
`vibration_high`). It combines a deterministic rule engine, a machine-learning
classifier, and a temporal fusion layer called CITA.

The scientific contribution is **not** a working crash predictor. When the system
is evaluated *correctly* (grouping all windows of one crash together so the model
cannot memorize the crash), it scores **at or below chance**. The real, defensible
result is therefore a **reproducible benchmark plus a study of evaluation
leakage, reported honestly as a negative result**.

The path to publishing that result is documented in
[`docs/PUBLICATION_PLAN.md`](PUBLICATION_PLAN.md). The v4 *toolchain* (the code
that produces and scores the benchmark) is already written and tested. What
remains is almost entirely **human, maintainer-only work**: collecting real forum
labels, confirming onset times, running the final evaluation, writing the paper,
and submitting it.

---

## 2. How to read this document

Each remaining task below has four parts:

- **Status** — where it stands today.
- **Completed so far** — what already exists (usually the tooling).
- **What is happening now** — whether any work is actively in progress.
- **What can still be done** — the concrete next actions, who owns them, and the
  bar for calling it done.

Status badges used: `[BUILT]` (code ready), `[PENDING]` (not started,
waiting on input), `[BLOCKED]` (cannot proceed until a dependency lands),
`[MAINTAINER-ONLY]` (requires the project owner's accounts/access).

---

## 3. Project state at a glance

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

---

## 4. Background that makes the rest make sense

- **v3 is the primary reproducible benchmark:** 34 logs / 32 incidents,
  AI-annotated, pre-registered. Honest incident-grouped macro-F1 is **0.056–0.069**
  for tree models; chance is **0.076**. Random-window splits (leaky) score
  **0.89–0.97** — that gap *is* the leakage effect.
- **v4 is a confirmatory holdout:** new incidents scored only on models/features/
  metrics frozen at v3. Its job is to confirm (or refute) the v3 conclusions on a
  larger, human-reviewed set. See [`docs/PREREGISTRATION_V4.md`](PREREGISTRATION_V4.md).
- **Every number must be reproducible** from one command at a clean commit,
  recorded in [`docs/EVIDENCE_LEDGER.md`](EVIDENCE_LEDGER.md). No label, onset,
  or metric may be fabricated.
- **The v4 toolchain is already built and tested** (14 passing tests):
  `training/build_benchmark_v4.py`, `training/propose_onsets.py`,
  `training/baselines/` (LogAnalyzer + LLM), `training/paper_eval.py
  --baselines-input`, and the pre-registration doc. It is described for readers in
  [`docs/BENCHMARK_GUIDE.md`](BENCHMARK_GUIDE.md).

---

## 5. Detailed remaining tasks

### Task A — Step 2: real forum labels + ≥100-incident gate + human spot-check/kappa

**Goal.** Produce ≥100 real incidents whose root cause is quoted from an actual
forum expert, human-review a random 20% (reporting Cohen's kappa), and assemble
`ground_truth_real_v4.json` — the input every later task needs.

**Status.** `[PENDING]` — not started.

**Completed so far.**
- `src/data/expert_label_miner.py` finds crash threads with `.bin` attachments.
- `training/fetch_adaptation_pool.py` downloads and SHA256-hashes logs (reads the
  existing `data/cohorts/cohort_manifest.json`, `adaptation_pool` cohort).
- `training/verify_thread_annotations.py` checks each label cites a real expert
  quote + permalink (exits 0 on success).
- `training/build_benchmark_v4.py` assembles the ground truth and **exits 2 if
  the labels file is missing** — it cannot fabricate data.
- `docs/PREREGISTRATION_V4.md` freezes the gate: ≥100 incidents, ≥5 per scored
  class, human-reviewed.

**What is happening now.** Nothing. No `thread_annotations_v4.json` exists yet;
the builder is intentionally blocked until it does.

**What can still be done.** (Maintainer + a second human reviewer.)
1. Curate a **per-class** query list — note `training/queries.json` is currently a
   flat list of 6 strings, not per-class; the rare classes
   (`ekf_failure`, `gps_quality_poor`, `brownout`, `thrust_loss`,
   `motor_imbalance`) need priority.
2. Run the miner to pull candidate threads; **discard its regex labels** (they are
   not valid root causes).
3. Download + hash logs via the cohort manifest.
4. Write each label with the expert's verbatim quote + post link into
   `thread_annotations_v4.json`.
5. `verify_thread_annotations.py --annotations thread_annotations_v4.json` must
   exit 0.
6. A human checks 20% randomly; compute Cohen's kappa; write
   `data/benchmark/SPOT_CHECK.md` (v4) + record it in `EVIDENCE_LEDGER.md`.
7. `build_benchmark_v4.py` → `ground_truth_real_v4.json` with ≥100 incidents, ≥5
   per class (use `--allow-missing-logs` only if some logs are undownloadable).

**Done when.** `thread_annotations_v4.json` has ≥100 quoted incidents;
verification exits 0; `SPOT_CHECK.md` (v4) reports kappa; `ground_truth_real_v4.json`
meets the gate.

---

### Task B — Step 3: human confirmation of ~30 onset proposals

**Goal.** Confirm ~30 onset-time proposals against the real logs and record
`onset_time_s`, enabling the CITA / onset-ordering test (hypothesis H3).

**Status.** `[BLOCKED]` — waits on Task A.

**Completed so far.**
- `training/propose_onsets.py` plots the relevant channel per label and proposes a
  threshold-crossing onset time; writes `data/benchmark/onset_proposals.json`.
- Nine labels auto-propose (`vibration_high, ekf_failure, gps_quality_poor,
  compass_interference, thrust_loss, motor_imbalance, mechanical_failure,
  power_instability, brownout`); four (`rc_failsafe, pid_tuning_issue,
  setup_error, crash_unknown`) return "no proposal" and are manual-only.

**What is happening now.** Nothing — needs `ground_truth_real_v4.json` from A.

**What can still be done.** (Maintainer.)
1. `propose_onsets.py --annotations ground_truth_real_v4.json
   --logs data/raw/benchmark_v4 --plots` → proposals + plots.
2. Maintainers inspect each plot; mark confirmed / adjusted / rejected.
3. Write `onset_time_s` into `data/benchmark/incidents.csv` and
   `ground_truth_real_v4.json`.
4. For unmapped labels, record a documented manual onset or N/A.
5. Compute onset-ordering accuracy → `EVIDENCE_LEDGER.md`.

**Done when.** ≥30 proposals inspected with saved plots; `onset_time_s` populated
for confirmed incidents; onset-ordering accuracy recorded.

---

### Task C — Step 5 (eval): confirmatory v4 evaluation run

**Goal.** Run the v4 evaluation exactly as pre-registered and report every
hypothesis (H1–H4) whatever the outcome, including a negative result.

**Status.** `[BLOCKED]` — waits on Tasks A + B.

**Completed so far.**
- `training/paper_eval.py` runs the full eval, records git commit + data hashes +
  seeds, and writes a traceable ledger JSON.
- Baselines (LogAnalyzer, LLM) are wired in behind `--baselines-input`.
- `docs/PREREGISTRATION_V4.md` states H1 (leakage), H2 (no method beats chance),
  H3 (CITA doesn't help), H4 (v4 within v3's CI 0.056–0.069).

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

---

### Task D — Step 5 (paper): expand to 10–14 pages

**Goal.** Turn the ~5-page draft into a real paper (related work, dataset
construction, annotation + agreement, per-class/error analysis, calibration,
threats to validity) and cite the dataset DOI.

**Status.** `[PENDING]` — authoring not started.

**Completed so far.**
- `paper/main.tex` exists (~5 pages) and builds via
  `python paper/make_figures.py` then `pdflatex` / `bibtex`.
- Author placeholder is at `main.tex` line 13; the Availability/DOI section is at
  lines 266–270.
- `CITATION.cff` has real title/abstract/license/version but a placeholder
  `authors:` block and **no `doi:` field**.
- `references.bib` entries were last checked against Crossref/arXiv on 2026-09-25
  (manual; no automated checker exists).

**What is happening now.** Nothing.

**What can still be done.** (Maintainer authors; assistant builds the PDF.)
1. Add the required sections.
2. Rebuild via `make_figures.py` + `pdflatex`/`bibtex`.
3. Re-verify `references.bib` (manual, dated).
4. Fill Availability with the Zenodo DOI (from Task E).
5. State v4 labels are human spot-checked (not "verified" until `SPOT_CHECK.md`
   v4 is complete).

**Done when.** `paper/main.pdf` is 10–14 pages with all sections; references
re-verified and dated; Availability cites the DOI; label status matches
`SPOT_CHECK.md` (v4).

---

### Task E — Step 1: arXiv preprint + Zenodo DOI

**Goal.** Archive the benchmark release on Zenodo (minting a DOI) and post an
arXiv preprint, with real authors and the DOI cited in the paper + `CITATION.cff`.

**Status.** `[PENDING]` — `[MAINTAINER-ONLY]` (Zenodo/arXiv accounts).

**Completed so far.**
- `training/make_release_bundle.py --version <v>` builds
  `dist/ardupilot-log-benchmark-v<v>.zip` (includes `DATASHEET.md`, which exists
  and is complete for v3).
- `CITATION.cff` is structured and ready for authors + DOI.

**What is happening now.** Nothing.

**What can still be done.** (Maintainer uses external accounts; assistant fills
fields.)
1. Replace author placeholders in `main.tex` + `CITATION.cff` with real name /
   affiliation / email.
2. `make_release_bundle.py --version 4.0` → zip (see Open Decision 1: 4.0 vs also
   a 3.0 snapshot).
3. Connect Zenodo to GitHub, publish the release, attach the zip, mint the DOI.
4. Add `doi:` to `CITATION.cff` and cite it in Availability.
5. Post the arXiv preprint (cs.LG, cross-listed cs.RO) with the DOI in Availability.

**Done when.** Zenodo DOI minted and archived; `CITATION.cff` has real authors +
`doi:`; arXiv preprint live citing the DOI.

---

### Task F — Step 6: journal submission

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

## 6. Cross-cutting notes

### 6.1 Dependency order
```
A (Step 2) ──► B (Step 3) ──► C (Step 5 eval) ──► D (Step 5 paper) ──► F (Step 6)
                │                            │                         ▲
                └────────────────────────────┘                         │
E (Step 1) needs the A bundle; its DOI must land in D's Availability. ──┘
```
Task A is the critical path — B, C, D all depend on its `ground_truth_real_v4.json`.

### 6.2 Open decisions to confirm
1. **Release version:** archive v4.0 (after A) vs also a v3.0 snapshot on Zenodo.
2. **Cohen's kappa:** reported honestly; no minimum score imposed (v3 was 0.39).
3. **"~30 onsets":** target may shift once the v4 label mix is known.
4. **LLM baseline API key:** `training/baselines/llm_baseline.py` reports "not run"
   without `ARDUPILOT_LLM_API_KEY`; confirm whether a key will be supplied.

### 6.3 Honesty constraints (non-negotiable)
- No fabricated labels, onsets, or metrics.
- Every published number reproducible from one command at a clean commit.
- A negative result (system at chance) is a valid, publishable outcome.

---

## 7. Out of scope (other roadmap tracks)

These are **not** part of the publication track and are untouched:
- **Milestone 2 — LLM orchestration:** planned but not built.
- **Milestone 5 — production hardening / release:** endpoint latency still exceeds
  the 500 ms gate (~2.3 s end-to-end vs ~433 ms pipeline; `hardware_report` is 71%
  of the payload). Milestone 3 (rule split, boundary tests, dead-label coverage,
  scaler decision) and Milestone 4 (bad-input handling) are already done/audited.
- **Milestone 6 — community adoption:** not started.

See `docs/UPGRADE_ROADMAP.md` for the full engineering roadmap.

---

## 8. Recommended starting point

Start with **Task A**, sub-step 1: curate the per-class query list. Everything
downstream is blocked on `ground_truth_real_v4.json`. The assistant can prepare
the exact commands as soon as the maintainer decides how threads will be sourced
(live forum scrape via the miner, or a set already collected).

---

## 9. Further reading

- [`docs/PUBLICATION_PLAN.md`](PUBLICATION_PLAN.md) — the full step-by-step plan.
- [`docs/BENCHMARK_GUIDE.md`](BENCHMARK_GUIDE.md) — accessible introduction to the
  benchmark.
- [`docs/EVIDENCE_LEDGER.md`](EVIDENCE_LEDGER.md) — every number + reproduction command.
- [`docs/PREREGISTRATION_V4.md`](PREREGISTRATION_V4.md) — the frozen v4 protocol + hypotheses.
- [`CORRECTIONS.md`](../CORRECTIONS.md) — retracted claims and why.
- `docs/UPGRADE_ROADMAP.md` — engineering roadmap (Milestones 0–6).
