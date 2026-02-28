# GSoC Mentor Questions — Exact Counter-Responses

> This document exists so that when the mentor asks something hard, you already
> know the precise, evidence-backed answer. Every response below is grounded in
> actual repo code, actual benchmark numbers, or actual decisions you have made.
> Never wing these questions. Cite the exact file and line.

---

## CATEGORY 1 — Benchmark & Data Quality

---

### Q1: "Your Macro F1 is 0.24. That's very low. Why should we trust this tool?"

**Why they ask it**: This is the single most likely opening question. It's a test of
whether you understand your own numbers or just copied them from a script.

**The wrong answer**: "It will improve with more data." (Generic. Sounds like excuses.)

**Your answer** (say this or write this):

> "The Macro F1 of 0.24 is the overall average across **8 labels**, but that average
> is heavily dragged down by three labels that are **mathematically untrainable** in
> this dataset: `gps_quality_poor` has **1 training example**, `pid_tuning_issue` has
> **2**, and `mechanical_failure` has **0**. No ML algorithm produces non-zero F1 from
> 1 example — that's a data problem, not a model problem.
>
> When we look at the labels that actually have enough training data:
> - `ekf_failure`: F1 = **0.67** (5 examples, 75% precision)
> - `compass_interference`: F1 = **0.57** (80% recall — finds 8/10 real cases)
> - `vibration_high`: F1 = **0.47** (9 examples)
>
> These are the operationally critical labels. A dropped prop or EMI spike killing a
> vehicle is caught. The 'theoretical' low Macro F1 is a consequence of including
> empty label columns in the macro average — standard practice in multi-label evaluation
> but misleading without this context.
>
> The improvement plan is concrete: **SMOTE** oversampling is now implemented in
> `training/train_model.py`, **GPS/PID forum mining** is the next data collection
> priority, and ECE measurement (`training/measure_ece.py`) is now automated."

**Evidence to cite**: `benchmark_results.json` lines 53–71, `progress_showcase.md` label distribution table.

---

### Q2: "How do I know your labels are correct? Did you make them up?"

**Why they ask it**: Fabricated labels are the most common academic dishonesty in ML projects.

**Your answer**:

> "Every benchmark label has a mandatory 4-part provenance record in the clean-import
> manifest: `source_url` (discuss.ardupilot.org thread), `resolved_download_url`
> (Google Drive or forum attachment), `sha256` hash (64 hex characters), and an
> `expert_quote` field capturing the verbatim developer or senior maintainer diagnosis
> from the thread.
>
> The data integrity audit in `docs/progress_showcase.md` shows zero integrity issues
> across all four batches — every label has all four fields with no empty entries.
>
> Additionally, `validate_leakage.py` performs SHA256 cross-comparison between the
> training set and the holdout set at the file level. The output for our current run:
> **0 overlapping SHAs, 13 unique train logs, 2 unique holdout logs.**
>
> The labeling policy itself (Root-Cause Precedence) is formally documented in
> `docs/root_cause_policy.md` and `docs/PRODUCTION_ACCEPTANCE_CRITERIA.md` — it is
> not ad-hoc, it is a defined rule applied consistently."

**Evidence to cite**: `docs/progress_showcase.md` data integrity table (0 issues, all 4 batches), `validate_leakage.py`, `docs/root_cause_policy.md`.

---

### Q3: "Your holdout set has only 2 logs. That's not a real holdout."

**Why they ask it**: This is true and they know it. The question is whether you know it and have a plan.

**Your answer**:

> "That's correct — and I documented it explicitly in `progress_showcase.md`:
> *'Holdout size caveat: 2 logs (small holdouts can produce high-variance metrics).'*
>
> The unseen holdout of 2 is the only set with mathematically verified zero SHA overlap
> with training. Achieving 1.00 F1 on it shows the model generalises correctly to
> the two label types it had enough training data for (vibration_high, compass_interference),
> but it cannot be used to claim general performance across 8 labels.
>
> This is exactly why **data expansion** is Priority 1 in the GSoC ML phase. The plan:
> targeted `mine-expert-labels` runs using `ops/expert_label_pipeline/` with GPS/PID-
> specific query sets to reach ≥ 5 examples per label before re-evaluating. The holdout
> target is N ≥ 50 with ≥ 2 examples of every label, as stated in
> `docs/PRODUCTION_ACCEPTANCE_CRITERIA.md`."

**Evidence to cite**: `docs/progress_showcase.md` line 78, `docs/PRODUCTION_ACCEPTANCE_CRITERIA.md` Section 3: Unseen Holdout Strategy.

---

### Q4: "Why do you have 4 vibration misclassified as compass? That's a systematic error."

**Why they ask it**: They read the confusion details in `benchmark_results.json`. This is
the most specific technical trap in your benchmark.

**Your answer**:

> "This is actually the most informative pattern in the entire confusion matrix, and it's
> expected. When vibration is severe — vibe_z_max above 60 m/s² — the physical vibration
> shakes the flight controller board, which causes the magnetometer to read noisy field
> values (the mag chip is physically on the same PCB). So a log labeled `vibration_high`
> by our root-cause policy will also show elevated `mag_field_range` and `mag_field_std`.
>
> The rule engine fires on both. Without the Temporal Arbiter, the engine picks the label
> with the highest confidence — often compass, because magnetic field range can spike to
> 500+ in high-vibration scenarios.
>
> The fix is already in `src/diagnosis/hybrid_engine.py`: the Temporal Arbiter compares
> `tanomaly` timestamps. If `vibe_z_tanomaly` is earlier than `mag_tanomaly`, vibration
> wins. This is the root of the 67% mislabeling finding in `docs/MAINTAINER_TRIAGE_REDUX.md`.
> Correct `tanomaly` extraction from the feature pipeline is the key engineering task in
> GSoC Phase 2."

**Evidence to cite**: `benchmark_results.json` confusion_details for `c648fe37de`, `7065a3cd0f`, `c1bcef192f`, `8265f254a7`, `hybrid_engine.py` lines 103–145.

---

## CATEGORY 2 — Technical Architecture

---

### Q5: "How is this different from DroneKit-LA, which already does rule-based analysis?"

**Why they ask it**: This is the 'why does this exist' question. Bad answer = no GSoC slot.

**Your answer**:

> "DroneKit-LA runs 15 fixed-threshold checks. It cannot detect cascading failures,
> provides no confidence scores, has no similarity retrieval, and has no ML component.
> Its EKF check uses a single hard threshold (`velocity_variance > 1.0`) that fires
> on many healthy logs in specific vehicle configurations.
>
> This project addresses three specific gaps:
> 1. **Root-cause disambiguation**: DroneKit-LA will flag both `vibration_high` and
>    `compass_interference` on a log where vibration caused the compass noise — giving the
>    user two contradictory instructions. Our Temporal Arbiter resolves to one root cause.
> 2. **Calibrated confidence**: Instead of Pass/Warn/Fail, every diagnosis has a 0–100%
>    confidence with evidence (exact feature, value, and threshold that fired). ECE target
>    is ≤ 0.08, measured by `training/measure_ece.py`.
> 3. **Forum case retrieval**: No existing tool links a diagnosis to resolved forum threads.
>    The retrieval engine in `src/retrieval/` will return top-3 similar cases with URLs —
>    a maintainer can immediately send a user to a solved case.
>
> The comparison table in the GSoC proposal (Section 6) documents this precisely."

**Evidence to cite**: `docs/gsoc_backup/GSOC_2025_Proposal.md` Section 6 comparison table, `hybrid_engine.py` temporal arbiter block, `training/measure_ece.py`.

---

### Q6: "Your confidence numbers — how are they calibrated? Are they real probabilities?"

**Why they ask it**: Most ML classifiers output uncalibrated softmax scores, not real probabilities.
A mentor who knows this will ask it.

**Your answer**:

> "This was a known gap until this week. The previous model output raw XGBoost softmax
> probabilities which are systematically overconfident. We have now added
> `CalibratedClassifierCV` with isotonic regression in `training/train_model.py`,
> which post-processes the softmax outputs into empirically validated probabilities.
>
> ECE measurement is fully automated in `training/measure_ece.py`. It computes
> Expected Calibration Error per class and macro, generates a reliability diagram,
> and exits with code 1 if ECE > 0.08. This will be a hard gate before any production
> benchmark claim — as soon as the training dataset has enough samples per class
> to support cross-validated calibration."

**Evidence to cite**: `training/train_model.py` lines for `CalibratedClassifierCV`, `training/measure_ece.py` the `compute_ece()` function and pass/fail logic.

---

### Q7: "What happens when someone runs this on a log type you've never seen before — a plane instead of a copter?"

**Why they ask it**: ArduPilot supports planes, rovers, submarines, helicopters. Your training data is copter-centric.

**Your answer**:

> "This is a deliberate scope constraint, not an oversight. The current scope is
> ArduCopter logs only. The feature pipeline extracts RCOU motor spread which is
> copter-specific (4+ motors in symmetric layout). Plane logs have a different RCOU
> interpretation (throttle + control surfaces).
>
> For out-of-scope vehicles, two safety mechanisms apply:
> 1. The rule engine applies absolute thresholds (vibe limits, EKF variance limits) that
>    are physically meaningful regardless of vehicle type — it won't hallucinate a
>    diagnosis, it'll return a conservative result.
> 2. The ML classifier will produce low-confidence output on an out-of-scope feature
>    distribution, which triggers the `uncertain` state in `decision_policy.py` and
>    the `UNCERTAIN — HUMAN REVIEW REQUIRED` output.
>
> ArduPlane support is explicitly listed as a stretch goal, not a core deliverable."

**Evidence to cite**: `src/diagnosis/decision_policy.py` `evaluate_decision()`, `src/cli/formatter.py` UNCERTAIN block, `AGENTS.md` stretch goals.

---

## CATEGORY 3 — GSoC Execution Risk

---

### Q8: "You said 242× faster triage. Show me exactly how you measured that."

**Why they ask it**: This is the headline claim in your triage study. If you can't reproduce the methodology, it's not science.

**Your answer**:

> "The triage study is documented in `docs/MAINTAINER_TRIAGE_REDUX.md`. The baseline of
> 8.5 minutes per log comes from a conservative estimate of manual expert review time:
> opening a log in Mission Planner's log viewer, scrolling through VIBE/MAG/EKF messages,
> identifying the anomaly, and forming a response — a common task for ArduPilot maintainers
> responding to forum threads.
>
> The 2.1 seconds per log is measured from CLI execution time of
> `python -m src.cli.main analyze <file.BIN>` on the benchmark set — parsing, feature
> extraction, hybrid diagnosis, and report formatting combined.
>
> The 45-log triage in 94 seconds vs ~6.5 hours manual is arithmetic: 45 × 8.5 min =
> 382.5 min = 6.375 hours. The actual tool time was 94/45 = 2.09 seconds per log.
>
> The caveat is explicit: the baseline is a conservative expert estimate, not a
> controlled experiment with timing measurements. A controlled before/after study
> with real maintainers timing their triage is `P4-02` in `AGENTS.md` and GSoC Week 11."

**Evidence to cite**: `docs/MAINTAINER_TRIAGE_REDUX.md` Section 2, `AGENTS.md` P4-02.

---

### Q9: "Can someone reproduce your results from scratch on a clean machine?"

**Why they ask it**: This is the reproducibility gate. If the answer is 'sort of', that's a problem.

**Your answer**:

> "Currently: mostly, but not fully automated. The full pipeline is:
> `git clone → pip install -r requirements.txt → python training/build_dataset.py →
> python training/train_model.py → python -m src.cli.main benchmark`.
>
> The blocker is that the training `.BIN` files are not committed to git (they're large
> binary files tracked via LFS provenance metadata instead). A mentor would need to
> re-run `python -m src.cli.main collect-forum` or use the Google Drive batch linked
> in `data/clean_imports/*/manifests/provenance_proof.md` to reconstruct the dataset.
>
> One-command reproducibility (`training/reproduce_benchmark.py`) is on the roadmap
> as U-11. During GSoC, the final benchmark will be fully reproducible — data download
> included — so any reviewer can verify."

**Evidence to cite**: `docs/UPGRADE_ROADMAP.md` U-11, `validate_leakage.py`, `docs/colab_quickstart.md`.

---

### Q10: "What if GSoC data collection targets (50+ logs per label) turn out to be too ambitious?"

**Why they ask it**: They want to see realistic contingency planning, not overconfidence.

**Your answer**:

> "The hard floor is 5 examples per label for SMOTE to work and for cross-validated
> calibration to be meaningful. For labels with < 5 examples, the rule engine
> carries the full diagnostic load — the ML classifier abstains on low-support labels.
>
> The contingency plan if forum mining can't reach 5 examples for rarer labels like
> `pid_tuning_issue` is SITL data augmentation: ArduPilot SITL supports
> `SIM_ENGINE_FAIL`, `SIM_ACC_RND`, `SIM_VIB_MOT_MAX` simulation parameters that
> can generate controlled synthetic failure logs. These are kept separate from real
> forum logs and clearly labeled `source_type: synthetic` in the manifest.
>
> The proposal (Section 5, Week 5) already includes SITL data generation as a
> fallback strategy. SITL data is already in the codebase via
> `training/generate_sitl_data.py`."

**Evidence to cite**: `docs/gsoc_backup/GSOC_2025_Proposal.md` Week 5 entry, `training/generate_sitl_data.py`, `training/train_model.py` `_safe_smote()` function.

---

## CATEGORY 4 — Safety & Trust

---

### Q11: "What if this tool says 'SAFE TO FLY' when the vehicle actually has a problem?"

**Why they ask it**: False negatives in flight safety tooling can kill vehicles and people.

**Your answer**:

> "This is the hardest category of failure and we have two explicit defences.
>
> First, a zero-confidence abstention: if the decision policy's `top_confidence` is
> below the `abstain_threshold` (default 0.65) **and** no rule engine check fired,
> the system outputs `UNCERTAIN — HUMAN REVIEW REQUIRED` rather than guessing HEALTHY.
> An ambiguous result is escalated, not silently passed.
>
> Second, False Critical Rate measurement (`training/measure_fcr.py`) works in the
> other direction — we measure how often the tool claims CRITICAL on a healthy log.
> FCR ≤ 10% is a hard production gate. False negatives are harder to enumerate
> directly (we can't know what we missed), but by measuring FCR we maintain the
> model's calibration — an overconfident model will have high FCR, and we catch it.
>
> The fundamental limitation is honest: this tool is a triage accelerator, not an
> airworthiness certifier. The CLI output always shows the evidence chain and recommends
> human review when uncertain. The output header will eventually carry a disclaimer:
> 'This tool assists analysis. It does not replace physical inspection.'"

**Evidence to cite**: `src/diagnosis/decision_policy.py` `abstain_threshold` parameter, `src/cli/formatter.py` UNCERTAIN block, `training/measure_fcr.py`, `docs/PRODUCTION_ACCEPTANCE_CRITERIA.md` FCR target.

---

### Q12: "What's your plan for integration with the actual ArduPilot project? Is this just a standalone CLI forever?"

**Why they ask it**: GSoC projects that don't integrate upstream often die after the summer.

**Your answer**:

> "The immediate deliverable is a standalone Python CLI with a clean public API
> (`src/diagnosis/hybrid_engine.py`). The integration strategy:
>
> **Phase 1 (GSoC):** Standalone CLI invokable by anyone from the ArduPilot discuss
> forum — users can run `pip install` and analyze their own logs before posting.
>
> **Phase 2 (post-GSoC):** MAVProxy module. MAVProxy has a Python module system — a
> `log_diagnosis.py` module could expose a `diagnose` command that runs the engine
> on the current log file within the MAVProxy session. This is documented as a stretch
> goal in the proposal (Week 11).
>
> **Phase 3:** Mission Planner integration. The JSON output format is designed for
> consumption by external tools. If a Mission Planner maintainer wanted to show
> diagnosis results in the UI, the JSON report is the integration surface.
>
> The key design decision that enables all of this: the engine is a Python class with
> a clean `diagnose(features: dict) -> list[dict]` interface. Any wrapping is trivial."

**Evidence to cite**: `docs/gsoc_backup/GSOC_2025_Proposal.md` Week 11 MAVProxy entry, `src/diagnosis/hybrid_engine.py` `HybridEngine.diagnose()` signature, `src/cli/formatter.py` `format_json()`.

---

## CATEGORY 5 — Personal & Commitment

---

### Q13: "Have you actually contributed to ArduPilot before?"

**Why they ask it**: ArduPilot mentors strongly prefer students who have already engaged with the community.

**Your answer** (fill in what's real for you):

> "Yes. I submitted a documentation PR adding Zorin OS troubleshooting to the SITL
> setup guide [link to PR], opened a pre-application discussion thread on
> discuss.ardupilot.org [link] to get feedback on the prototype before applying,
> and have been active in the #gsoc Discord channel sharing prototype benchmarks.
>
> Beyond community engagement, I have studied the relevant source code:
> `Tools/LogAnalyzer/LogAnalyzer.py`, `libraries/AP_Logger/LogStructure.h` (all
> message format definitions), `libraries/AP_NavEKF2/` and `AP_NavEKF3/` (EKF
> implementation to understand what the variance fields actually measure), and the
> SITL simulation parameters to validate that my feature thresholds are grounded in
> the actual firmware behavior."

**Evidence to cite**: Your actual PR link. This one you cannot fake — have the link ready.

---

### Q14: "What will you do if you fall behind schedule mid-summer?"

**Why they ask it**: This is a soft question about reliability and communication.

**Your answer**:

> "I have already built more than the Week 4–5 deliverables in the proposal before
> coding officially starts. The prototype has: working parser, 60+ feature pipeline,
> rule engine v2, hybrid fusion engine, Temporal Arbiter, calibration, benchmark runner,
> CI, and 56 passing tests. This buffer exists specifically because I know ML data
> collection is the hardest-to-predict variable.
>
> If I fall behind on data collection specifically: the rule-only engine is already
> production-quality for 6 out of 8 labels. I will not hide schedule drift — the
> weekly operating rhythm in `AGENTS.md` includes a Friday benchmark snapshot on every
> session. If a metric regresses or a timeline slips, it will be in the weekly report
> before the mentor asks."

**Evidence to cite**: `AGENTS.md` weekly operating rhythm section (session log template), `docs/PLAN-gsoc-architecture.md` task completion board (most tasks already ✅).

---

## WHAT TO MEMORISE (The 10 numbers that win the conversation)

| Fact | Number | Where |
|---|---|---|
| Total benchmark logs | 45 | `benchmark_results.json` |
| Compass recall | 80% | `benchmark_results.json` |
| EKF precision | 75% | `benchmark_results.json` |
| Train/holdout SHA overlaps | **0** | `validate_leakage.py` |
| Tests passing | **56** | `pytest -q` output |
| Triage speedup | **242×** | `MAINTAINER_TRIAGE_REDUX.md` |
| GPS training examples | **1** | `progress_showcase.md` (explains low F1) |
| ECE target | **≤ 0.08** | `PRODUCTION_ACCEPTANCE_CRITERIA.md` |
| FCR target | **≤ 10%** | `PRODUCTION_ACCEPTANCE_CRITERIA.md` |
| Mislabeled-as-symptom rate | **67%** | `MAINTAINER_TRIAGE_REDUX.md` Section 3 |
