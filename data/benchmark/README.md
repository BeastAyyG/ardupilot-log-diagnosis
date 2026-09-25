# Real-Log Benchmark v1 (provisional)

An incident-level registry of **real** ArduPilot flight logs with root-cause
labels, built reproducibly from committed, hash-checked inputs. Simulated
flights (BASiC, SITL) are excluded.

**Status:** provisional. Most labels are not yet tied to a written expert
diagnosis (see "Evidence tiers"). Treat any score computed on this set as a
development estimate, not a publishable result.

## Rebuild

```bash
git lfs pull                       # 43 real logs stored with Git LFS
python training/build_incident_registry.py --stage-dir data/raw/benchmark_v1
python training/build_dataset.py \
  --ground-truth data/benchmark/ground_truth_real_v1.json \
  --dataset-dir data/raw/benchmark_v1 \
  --features-out data/benchmark/derived/features.csv \
  --labels-out data/benchmark/derived/labels.csv \
  --groups-out data/benchmark/derived/groups.csv \
  --report-out data/benchmark/derived/dataset_build_report.json
python training/paper_eval.py --output data/benchmark/results/paper_eval_v1.json
```

`data/raw/` is git-ignored. Raw logs are never committed.

Some logs are not stored in the repository: the 5 in
`data/raw/history_recovered/` and the 3 in `data/raw/redownloaded/`. Restore
them as follows, then check each file's SHA256 against `incidents.csv`:
- **History-recovered:** `git show b7c7294^:data/clean_imports/background_expert_01/benchmark_ready/dataset/log_00NN_mechanical_failure.bin`, for NN = 37–41.
- **Re-downloaded:** fetch from each row's `download_url`.

## Current results

See [`docs/EVIDENCE_LEDGER.md`](../../docs/EVIDENCE_LEDGER.md) and
`results/paper_eval_v1.json` (commit `38d342e`).
- **ML at chance:** incident-grouped log macro-F1 is 0.08–0.09, against a
  random-guess baseline of 0.10.
- **Leakage:** the same models score 0.89 when windows are split at random.
- **Rule engine:** 0.16.
- **CITA:** no measurable benefit.

## Files

| File | Content |
|---|---|
| `incidents.csv` | One row per labelled real log: SHA256, incident, source, original and corrected labels, evidence tier, review verdict, exclusion reason, local availability |
| `ground_truth_real_v1.json` | The evaluable, locally available subset, in the format `training/build_dataset.py` reads |
| `registry_summary.json` | Counts used in reports |
| `label_corrections.json` | Every label change, with the commits that show the original and changed value |
| `llm_quote_review.json` | Secondary machine review of stored quotes (needs human confirmation) |
| `derived/` | Window-level feature matrices and cached per-log features (derived data, no raw telemetry) |
| `results/` | Evaluation outputs from `training/paper_eval.py` |

The source of truth for cohort membership is
`data/cohorts/cohort_manifest.json`. Its seal (`e68b962a…`) is verified on
every build.

## Label policy

1. A label must come from a human: the forum thread or this project's author.
   It must never come from this project's rule engine. Three rule-engine
   overwrites are reverted (`label_corrections.json`; CORRECTIONS.md, C8).
2. **Incident** = source thread or issue. All logs from one incident stay on
   the same side of any split.
3. A log is excluded from evaluation when:
   - it has more than one label;
   - its incident carries conflicting labels (thread `/50267`: motor vs power);
   - its own quoted source contradicts the label (thread `/101680`: the
     "diagnosis" is a plan to test dead reckoning);
   - its incident is contaminated (thread 142590; CORRECTIONS.md, C5).

Reverting the three rule-engine overwrites removed three of the four
"contradictory incidents" reported earlier (CORRECTIONS.md, C9).

## Evidence tiers

| Tier | Meaning |
|---|---|
| `named_user_quote` | A post by a named forum user is stored. It still needs a human check that it supports the label. |
| `author_summary` | Only this project's own paraphrase of the thread is stored. |
| `none` | No supporting text is stored. The label may come from the forum search term used to find the log. |

The counts per tier are in `registry_summary.json`. **Raising logs to a
verified tier is the main Phase 2 labelling task.** For each log, the
labeller reads the thread, records the diagnosing post (its URL and author),
and confirms or corrects the label.

## Licensing

Redistribution rights for the raw logs are **unverified**
(`licence_status = unverified`). Share the registry and derived features.
Do not share the raw logs without the owner's permission.
