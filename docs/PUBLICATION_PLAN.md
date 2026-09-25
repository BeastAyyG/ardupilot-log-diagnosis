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
| 2. Dataset v1 | ≥ 100 real incidents with expert quote, SHA256, onset time, licence status; agreement study | **Started.** Registry has 41 usable logs / 37 incidents with evidence tiers; 27 of 41 labels have no stored diagnosis, so a labelling pass is next |
| 3. Experiments | Leakage "staircase"; baselines incl. hybrid with and without CITA; onset-ordering accuracy; calibration and abstention | **Pilot run on v1:** split-protocol staircase (0.89 → 0.17 → 0.09), CITA on/off, chance baselines. Label-contamination steps and onset accuracy still to do |
| 4. Paper | Preprint and dataset DOI, then journal submission | Not started |

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
is run on the frozen holdout.

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
