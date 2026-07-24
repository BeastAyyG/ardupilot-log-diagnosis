# GSoC Mentor Questions - Exact Counter-Responses

> This file exists so the mentor questions do not catch you off guard. Every answer
> below is grounded in the current repo artifacts and the July 24, 2026 audit results.

---

## CATEGORY 1 - Benchmark and data quality

### Q1: "Your Macro F1 is 0.603. Why should we trust this tool?"

> "You should not trust the ML score by itself yet. The calibrated macro F1 is 0.603
> on a saved, group-isolated holdout of 22 flights, and no flight_id is shared with the
> 88-flight training fold.
>
> The result is promising for gps_quality_poor and rc_failsafe, but the holdout
> contains only one motor_imbalance and one power_instability flight; both scored zero
> F1. The top-label ECE is 0.1268, so the <= 0.08 calibration gate is still open.
>
> The useful trust boundary is the hybrid design: ML is advisory, physics rules show
> exact telemetry evidence, CITA orders anomaly onset, and low-confidence or ambiguous
> results explicitly require human review."

Evidence to cite: `training/evaluation_report.md`, `training/ece_report.json`,
`models/manifest.json`.

### Q2: "How do I know your labels are correct? Did you make them up?"

> "Every benchmark label has a mandatory 4-part provenance record in the clean-import
> manifest: source_url, resolved_download_url, sha256 hash, and an expert_quote field.
>
> The July 24 candidate review re-checked 24 provisional entries; 2 were promoted to
> human_verified: true and 22 were skipped, rejected, or left unverified. Nothing enters
> training unless it passes both provenance checks and human review.
>
> Additionally, validate_leakage.py performs SHA256 cross-comparison between the
> training set and the holdout set at the file level. The current manifest still reports
> 0 overlapping SHAs."

Evidence to cite: `data/to_label/review_report_2026-07-24.md`, `validate_leakage.py`,
`docs/root_cause_policy.md`.

### Q3: "Your holdout set has only 2 logs. That's not a real holdout."

> "That was true in an earlier snapshot, but it is no longer true. The current saved
> holdout is 22 flights with 88 train / 22 test and no shared flight_id.
>
> The real caveat now is class support inside that holdout: motor_imbalance and
> power_instability still have only one test flight each, so their F1 can swing a lot.
> That is why the calibration gate is still open even though the split itself is clean."

Evidence to cite: `models/manifest.json`, `training/evaluation_report.md`,
`training/ece_report.json`.

### Q4: "Why did thrust_loss get missed in the release benchmark?"

> "The 6-log release smoke benchmark is tiny, and thrust_loss is the weakest label in it.
> On `log_0046_thrust_loss.bin`, the engine recovered the downstream motor_imbalance and
> power_instability signals, but it missed the parent thrust_loss label.
>
> That is reflected in `release_benchmark_results.json`: any-match and top-1 are both
> 1.0, exact-match is 0.67, and macro F1 is 0.81. The fix is more verified thrust-loss
> examples, not changing the arbitration logic."

Evidence to cite: `release_benchmark_results.md`, `release_benchmark_results.json`.

---

## CATEGORY 2 - Technical architecture

### Q5: "How is this different from DroneKit-LA, which already does rule-based analysis?"

> "DroneKit-LA runs fixed-threshold checks. It does not provide calibrated confidence,
> similarity retrieval, or ML-backed ranking of ambiguous cases.
>
> This project adds three things:
> 1. Root-cause disambiguation using the temporal arbiter.
> 2. Calibrated confidence with a real ECE gate.
> 3. Forum case retrieval for similar solved incidents."

Evidence to cite: `docs/gsoc_backup/GSOC_2025_Proposal.md`, `hybrid_engine.py`,
`training/measure_ece.py`.

### Q6: "Your confidence numbers - how are they calibrated? Are they real probabilities?"

> "The current small-data model uses CalibratedClassifierCV with sigmoid calibration.
> Median imputation and calibration are fitted without touching the saved outer holdout.
>
> `training/measure_ece.py` uses the exact unseen flight_id values stored in the model
> manifest, computes top-label ECE, generates a reliability diagram, and exits with code
> 1 if ECE > 0.08. The current ECE is 0.1268, so these probabilities are advisory and
> uncertain cases require human review."

Evidence to cite: `training/train_model.py`, `training/measure_ece.py`.

### Q7: "What happens when someone runs this on a log type you've never seen before - a plane instead of a copter?"

> "This is a deliberate scope constraint, not an oversight. The current scope is
> ArduCopter logs only.
>
> For out-of-scope vehicles, two safety mechanisms apply:
> 1. The rule engine applies physically meaningful thresholds and returns conservative
>    results instead of hallucinating a diagnosis.
> 2. The ML classifier produces low-confidence output on an out-of-scope distribution,
>    which triggers the uncertain state and human review."

Evidence to cite: `src/diagnosis/decision_policy.py`, `src/cli/formatter.py`.

---

## CATEGORY 3 - Execution risk

### Q8: "You said you have an 84% reduction in triage time. Show me exactly how you measured that."

> "The triage study is documented in `docs/MAINTAINER_TRIAGE_REDUX.md`. The baseline of
> 8.5 minutes per log comes from a conservative estimate of manual expert review time.
>
> The 2.1 seconds per log is measured from CLI execution time of
> `python -m src.cli.main analyze <file.BIN>` on the benchmark set - parsing, feature
> extraction, hybrid diagnosis, and report formatting combined.
>
> The 45-log triage in 94 seconds vs about 6.5 hours manual is arithmetic. The caveat is
> explicit: the baseline is a conservative expert estimate, not a controlled timing
> experiment."

Evidence to cite: `docs/MAINTAINER_TRIAGE_REDUX.md`.

### Q9: "Can someone reproduce your results from scratch on a clean machine?"

> "Mostly, but not fully automated yet. The full pipeline is:
> `git clone -> pip install -r requirements.txt -> python training/build_dataset.py ->
> python training/train_model.py -> python -m src.cli.main benchmark`.
>
> The blocker is that the training BIN files are not committed to git. A reviewer must
> reconstruct the dataset from the provenance artifacts or the backup source."

Evidence to cite: `docs/UPGRADE_ROADMAP.md`, `docs/colab_quickstart.md`.

### Q10: "What if GSoC data collection targets (50+ logs per label) turn out to be too ambitious?"

> "The hard floor is 5 examples per label for SMOTE to work and for cross-validated
> calibration to be meaningful. For labels with fewer than 5 examples, the rule engine
> carries the full diagnostic load and the ML classifier abstains on low-support labels.
>
> If forum mining cannot reach that floor, SITL data augmentation is the fallback."

Evidence to cite: `training/train_model.py`, `training/generate_sitl_data.py`.

---

## CATEGORY 4 - Safety and trust

### Q11: "What if this tool says SAFE TO FLY when the vehicle actually has a problem?"

> "This is the hardest category of failure and we have two explicit defences.
>
> First, a zero-confidence abstention: if top_confidence is below the abstain threshold
> and no rule engine check fired, the system outputs UNCERTAIN - HUMAN REVIEW REQUIRED
> rather than guessing HEALTHY.
>
> Second, False Critical Rate measurement works in the other direction - we measure how
> often the tool claims CRITICAL on a healthy log. FCR <= 5% is a hard production gate."

Evidence to cite: `src/diagnosis/decision_policy.py`, `training/measure_fcr.py`,
`docs/PRODUCTION_ACCEPTANCE_CRITERIA.md`.

---

## CATEGORY 5 - Personal and commitment

### Q14: "What will you do if you fall behind schedule mid-summer?"

> "I have already built more than the Week 4-5 deliverables in the proposal before
> coding officially starts. The prototype has: working parser, feature pipeline, rule
> engine, hybrid fusion engine, calibration, benchmark runner, CI, and 219 passing tests.
>
> If I fall behind on data collection specifically, the rule-only engine is already
> production-quality for 6 out of 8 labels. I will not hide schedule drift - the weekly
> operating rhythm in `AGENTS.md` includes a Friday benchmark snapshot on every session."

Evidence to cite: `AGENTS.md`, `docs/PLAN-gsoc-architecture.md`.

---

## WHAT TO MEMORIZE

| Fact | Number | Where |
|---|---|---|
| Total benchmark logs | 6 | `release_benchmark_results.json` |
| Top-1 accuracy | 100% | `release_benchmark_results.json` |
| Exact-match accuracy | 67% | `release_benchmark_results.json` |
| Macro F1 | 0.81 | `release_benchmark_results.json` |
| Train/holdout SHA overlaps | 0 | `validate_leakage.py` |
| Tests passing | 219 | `pytest -q` output |
| Human-reviewed promotions | 2 | `data/to_label/review_report_2026-07-24.md` |
| Triage time reduction | 84% | `docs/MAINTAINER_TRIAGE_REDUX.md` |
| ECE target | <= 0.08 | `docs/PRODUCTION_ACCEPTANCE_CRITERIA.md` |
| FCR target | <= 5% | `docs/PRODUCTION_ACCEPTANCE_CRITERIA.md` |
