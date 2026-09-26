# Roadmap to a Publishable Result

**Goal:** a reproducible, incident-level benchmark for ArduPilot crash
root-cause diagnosis (A). It is paired with a controlled study of how
evaluation leakage inflates reported accuracy in this field (B).

**Principles:**
- Every published number lives in [EVIDENCE_LEDGER.md](EVIDENCE_LEDGER.md).
- Every retracted number stays explained in [CORRECTIONS.md](../CORRECTIONS.md).

## Status

| Phase | Deliverable | Status |
|---|---|---|
| 0. Credibility | Corrections published; unsupported claims removed; evidence ledger | **Done** (2026-09-25) |
| 1. Reproducibility | Full history fetched; 47/55 labelled real logs recovered and hash-verified; incident registry; CITA ablation switch; `training/paper_eval.py`; baseline regenerated from one command (the old 0.500 is superseded) | **Done** (2026-09-25) |
| 2. Dataset v1 | ≥ 100 real incidents with expert quote, SHA256, onset time, licence status; agreement study | **v3:** 34 logs / 32 incidents with cited, AI-annotated labels; kappa 0.39 vs old labels. **v4 build/label toolchain implemented** (`training/build_benchmark_v4.py`, `training/propose_onsets.py`, `training/baselines/`; 14 tests pass). Still maintainer-only: real forum labels, ≥100 incidents, human spot-check, onset times |
| 3. Experiments | Leakage "staircase"; baselines incl. hybrid with and without CITA; onset-ordering accuracy; calibration and abstention | **Done for v3 (pre-registered):** H1–H3 supported. **v4 missing-baseline toolchain implemented** (LogAnalyzer + LLM baselines in `paper_eval.py --baselines-input`; onset proposer). Still maintainer-only: human onset confirmation + confirmatory holdout evaluation |
| 4. Paper | Preprint and dataset DOI, then journal submission | **Draft compiled** (`paper/main.pdf`). arXiv/Zenodo preprint and journal submission are **maintainer-only external actions**. Toolchain for Steps 2–5 implemented; author details, reference checks, spot-check and venue template pending |

## Phase 1: Reproducibility

1. Recover `models/candidates/` and `data/ablation/` manifests from the
   original machine, if they still exist.
2. Restore the real logs into a git-ignored directory. Logs are no longer
   committed.
3. Rebuild `training/{features,labels,groups}.csv` with `incident_id`,
   `source_url` and `source_type` (real / basic / sitl). Reuse the
   thread-grouping key from `data/cohorts/cohort_manifest.json` on branch
   `goal-loop-results`.
4. Move thread 142590 out of every evaluation holdout (CORRECTIONS.md, C5).
5. Add `training/paper_eval.py`. It reuses `training/evaluation_split.py`,
   `training/run_model_experiments.py` and `training/measure_ece.py`, plus
   the bootstrap from `synthetic_data/ablation_core.py`. It writes one JSON
   per run containing the commit, data hash, seed, metrics and 95% CIs.
6. **Gate:** the 0.500 / 0.153 baseline is regenerated, or retracted.
   **Outcome:** it could not be regenerated and is superseded (C12). The
   reproducible benchmark is at chance level for ML (0.08–0.09 vs 0.10).
   It shows a large leakage effect: 0.89 with random window splits.

## Phase 2: Dataset v1 (paper A)

**Registry.** `data/benchmark/incidents.csv` has one row per incident:
- Identity: `incident_id`, `source_url`, `log_sha256`, `download_url`.
- Vehicle: `vehicle`, `firmware`.
- Labels: `root_cause`, `secondary_symptoms`, `onset_time_s`.
- Evidence: `expert_quote`, `expert_role`, `evidence_tier`.
- Status: `licence_status`, `split`.

**Labels:**
- Labels come only from written expert diagnoses. Never from the rule engine
  (CORRECTIONS.md, C8).
- Contradictory threads are resolved from the thread text or excluded, with
  the reason written down (C9).
- Simulated data (BASiC, SITL) is a separate track. It is never pooled with
  real incidents.

**Agreement:** three independent label sources:
1. The forum expert's written diagnosis.
2. A blind log inspection, recorded before the thread is read.
3. LLM extraction from the thread text, used as a check only.

Report Cohen's / Fleiss' kappa and state the single-annotator limitation.

**Onset:** record the onset time of the root cause and of each symptom,
annotated from the log with a saved plot. This is what makes CITA testable.

**Licensing:**
- Raw logs are not redistributed without the owner's permission.
- The release contains URLs, SHA256 hashes, a download ("hydration") script,
  derived features, labels and onsets.
- It is archived on Zenodo with a datasheet.

## Phase 3: Experiments

**Preregistration.** `docs/PREREGISTRATION.md` is committed before anything
is run on the frozen holdout. v4 extends this in
[`docs/PREREGISTRATION_V4.md`](PREREGISTRATION_V4.md): it freezes v3's
models, features and metrics and scores v4 only on new incidents, making v4 a
confirmatory holdout (not a tuning set).

**Leakage study (B).** The same models are evaluated under progressively
stricter protocols:
1. Window-level random split.
2. Filename grouping.
3. Incident grouping.
4. Contradictory labels removed.
5. Simulated logs excluded from the test set.
6. Rule-derived labels reverted.

Report Macro F1 and ECE with bootstrap CIs at each step.

**Benchmark (A).** Baselines:
- Majority class.
- Rules only.
- ML only (RandomForest, ExtraTrees).
- Hybrid.
- Hybrid without CITA (`--engine hybrid_no_cita`).
- External rule-based analysers, where their outputs map to the label set.
- An LLM given the structured report.

Also measure onset-ordering accuracy, abstention and coverage, and
calibration. Classes with n < 5 are reported but flagged as unreliable.

## Phase 4: Publication

Order of release:
1. arXiv preprint, with a dataset DOI.
2. Submission to a journal that publishes dataset-and-benchmark work.
3. Check the journal's current quartile at submission time.

**Acceptance bar before submitting:** one command regenerates every table and
figure from the frozen data, and the numbers match the manuscript.

## Next steps (as of 2026-09-25)

Current state:
- Benchmark v3 is merged: 34 real logs from 32 incidents.
- The pre-registered results support H1–H3.
- References are verified.
- A datasheet, `CITATION.cff`, log hydration (33/34 logs verified), and a release bundle are in place.

What a Q1 reviewer would still reject:
- The dataset is small.
- The labels are machine-only.
- There is no confirmatory holdout.
- There are no onset times.
- Two baselines are missing.
- The paper is 5 pages.

### Step 1: Preprint and DOI (week 1). Maintainer only — external.

1. Complete `data/benchmark/SPOT_CHECK.md` and add the agreement rate to `docs/EVIDENCE_LEDGER.md` and to Section 4 of the paper.
2. Replace the author placeholders in `paper/main.tex` and `CITATION.cff`.
3. Connect Zenodo to GitHub and publish the GitHub release `benchmark-v3.0`. Attach the zip from `python training/make_release_bundle.py --version 3.0`.
4. Cite the DOI in the paper's Availability section, then post the preprint to arXiv (cs.LG, cross-listed to cs.RO).

### Step 2: Scale to at least 100 incidents (weeks 1–4)

1. **Pre-register first.** Commit `docs/PREREGISTRATION_V4.md` before any new label. It must freeze v3's models, features and metrics, and state that v4 is scored only on new incidents. This makes v4 a confirmatory holdout.
2. **Find candidates.** Search the forum for crash threads with a `.bin` attachment, using `_search_topics` in `src/data/expert_label_miner.py`. Use about 5 queries per class in `training/queries.json`, with priority on the rare classes: ekf_failure, gps_quality_poor, brownout, thrust_loss and motor_imbalance. Discard the miner's regex labels (see CORRECTIONS.md, C8 and C11).
3. **Download.** Fetch and hash-check each log with the logic in `training/fetch_adaptation_pool.py`.
4. **Label.** Follow the existing protocol: diagnosing post, permalink, verbatim quote and certainty. Store the labels in `data/benchmark/thread_annotations_v4.json`. Verify them with `training/verify_thread_annotations.py`.
5. **Build.** Write `training/build_benchmark_v4.py`, keeping one label per incident. Add tests that follow the v3 tests.
6. **Human check.** The maintainer checks a random 20% of the new labels. Report Cohen's kappa.

**Gate:** at least 100 incidents, and at least 5 incidents per class that is scored. Smaller classes are merged, or reported as unreliable.

### Step 3: Onset times (weeks 3–5)

- `training/propose_onsets.py` plots the channels relevant to each label and proposes an onset time.
- The maintainer confirms about 30 of these proposals.
- Report onset-ordering accuracy. This is the direct test of CITA (H3).

### Step 4: Missing baselines (weeks 4–5)

- **ArduPilot's own log checks.** `Tools/LogAnalyzer` is no longer at its old path in the ArduPilot repository. First confirm whether it was moved or removed, and what replaced it. Then map its verdicts to our labels in a documented table.
- **LLM baseline.** An LLM reads the structured report, with a fixed prompt and temperature 0. This needs an API key stored as an environment secret. If no key is available, the paper says this baseline was not run.
- Add both baselines to `training/paper_eval.py` behind `--models`.

  **Implemented (2026-09-26):** the LogAnalyzer and LLM baselines live in
  `training/baselines/` (`loganalyzer_map.py`, `llm_baseline.py`) and are wired
  into `training/paper_eval.py` behind the `--baselines-input` flag (default:
  not scored, so the default run is unchanged). The LogAnalyzer path is a
  static, conservative map from its checks to our labels; the LLM baseline is
  gated on `ARDUPILOT_LLM_API_KEY` and reports "not run" when the key is unset.

### Step 5: Confirmatory evaluation and full paper (weeks 5–7)

- Run the v4 evaluation exactly as pre-registered, and report every hypothesis whatever the outcome.
- If v4 is still at chance, publish as benchmark + leakage study + negative result.
- Expand the paper to 10–14 pages. Add related work, dataset construction, the annotation protocol and agreement, per-class and error analysis, calibration, and threats to validity.
- Check every number against `docs/EVIDENCE_LEDGER.md`.

### Step 6: Submission (week 8). Maintainer only — external.

- **Venue.** Candidates are *Engineering Applications of Artificial Intelligence* and *Reliability Engineering & System Safety*. Check the quartile on Scimago on the day you submit. Avoid *Scientific Data*: it requires open raw data, and the log licences are unverified.
- **Package.** Port the paper to the venue template, then write the cover letter.
- **Licensing.** Ask the log owners on the forum for permission to redistribute their logs.

## Scope and assumptions (as of 2026-09-26)

The publication toolchain for Steps 2–5 is implemented in code. What was and
was not done:

**Implemented (code + tests, no fabricated data):**
- `docs/PREREGISTRATION_V4.md` — pre-registration for the confirmatory holdout.
  Freezes v3's models, features and metrics; v4 is scored only on new
  incidents. No number is predicted in advance beyond "report every hypothesis
  whatever the outcome".
- `training/build_benchmark_v4.py` — mirrors the v3 builder; consumes
  `data/benchmark/thread_annotations_v4.json` + `ground_truth_real_v3.json`,
  drops conflicted incidents, and exits with code 2 (a clear error, no
  fabrication) if the v4 annotations file is absent. Flag `--allow-missing-logs`
  supports the maintainer phase when logs cannot yet be downloaded.
- `training/propose_onsets.py` — plots label-relevant channels and proposes an
  onset time from domain thresholds. Unmapped labels (setup_error,
  crash_unknown, rc_failsafe, pid_tuning_issue, healthy) return `None` and are
  maintainer-confirmed only.
- `training/baselines/` (`loganalyzer_map.py`, `llm_baseline.py`) — LogAnalyzer
  and LLM baselines; wired into `training/paper_eval.py` behind `--baselines-input`.
- 14 new tests (`test_build_benchmark_v4.py`, `test_propose_onsets.py`,
  `test_baselines.py`) pass (`python -m pytest -q`).

**Not done (require maintainer-only external actions):**
- Real forum labels for new incidents, the ≥100-incident gate, and the human
  spot-check / kappa (Step 2.6, Step 3).
- Human confirmation of ~30 onset proposals (Step 3).
- The confirmatory v4 evaluation run and the full 10–14 page paper (Step 5).
- arXiv preprint, Zenodo DOI, and journal submission (Steps 1, 6).

**Assumptions made:**
1. No incident label, onset time, or evaluation number was invented. Every
   runnable artifact follows the evidence-ledger rule: a number is published
   only when a single command regenerates it from committed code and data.
   Where real inputs are missing, the code errors clearly instead of fabricating.
2. The LogAnalyzer baseline is a static map from its documented checks to our
   label set; it is conservative and may report "cannot score" for logs whose
   checks do not map.
3. The LLM baseline is opt-in (API key) and reports "not run" otherwise, so the
   paper's negative-result framing is preserved even without a key.
4. v4 is treated strictly as a confirmatory holdout. Its models/features/metrics
   are frozen at v3; new incidents are scored, never used to retune.
