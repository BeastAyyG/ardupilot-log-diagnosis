# Evidence Ledger

**Rule:** every performance number in the README, model card or a paper must
appear in this ledger with:
- the committed artifact it comes from;
- the single command that regenerates it;
- the commit it was produced at.

A number without a complete row is not a result. It must not be published,
or it must be marked "unverified".

Status values:
- **Reproducible:** the command regenerates the artifact from committed code
  and data.
- **Text-only:** the number exists in documentation, but its artifact or
  inputs are missing from the repository.
- **Retracted:** see [CORRECTIONS.md](../CORRECTIONS.md).

## Reproducible results (real-log benchmark v1)

All rows come from
[`data/benchmark/results/paper_eval_v1.json`](../data/benchmark/results/paper_eval_v1.json),
produced at commit `38d342e` (clean tree).
- **Command:** `python training/paper_eval.py`. The rebuild steps are in
  [`data/benchmark/README.md`](../data/benchmark/README.md).
- **Data:** 41 real logs from 37 incidents, 10 classes. Labels are
  **provisional** (CORRECTIONS.md, C11).
- **Metric:** log-level macro-F1 over the classes present. Brackets give a
  95% incident-cluster bootstrap CI.
- **Determinism:** re-running under two different `PYTHONHASHSEED` values
  gave identical metrics. The only differences were in the 17th decimal place
  of two ECE values.

| Claim | Value | Status |
|---|---|---|
| Chance: always predict the majority class | 0.033 | Reproducible |
| Chance: random guess by label frequency | mean 0.096 (95th percentile 0.175) | Reproducible |
| RandomForest, windows split at random (leaky) | 0.890 ± 0.002 (5 seeds) | Reproducible |
| RandomForest, grouped by log file | 0.169 ± 0.006 | Reproducible |
| **RandomForest, grouped by incident** | **0.092 ± 0.007** (seed 42 CI 0.04–0.15); ECE 0.082 | Reproducible |
| ExtraTrees, windows split at random (leaky) | 0.893 ± 0.002 | Reproducible |
| ExtraTrees, grouped by log file | 0.144 ± 0.004 | Reproducible |
| **ExtraTrees, grouped by incident** | **0.078 ± 0.007** (seed 42 CI 0.03–0.12); ECE 0.079 | Reproducible |
| Rule engine alone (no trained model) | 0.159 [0.083, 0.278]; 9/41 correct; 97.6% coverage | Reproducible |
| Rules + fusion, CITA on | 0.090 [0.040, 0.168]; 8/41 correct | Reproducible |
| Rules + fusion, CITA off | 0.138 [0.069, 0.243]; 8/41 correct; CITA changed 20 of 41 top-1 predictions | Reproducible |
| Shipped hybrid model | 0.103; **contaminated**: trained on these logs, must not be cited | Diagnostic only |

**Reading these numbers:**
- Splitting windows at random makes the same model look about ten times
  better (0.89) than grouping by incident (0.08–0.09). That is the leakage
  effect.
- With incident grouping, neither the tree models nor the rule engine beats
  the frequency-random baseline's 95th percentile.
- CITA shows no measurable benefit on these labels.
- Every one of these conclusions is limited by 41 logs and provisional labels.

## Reproducible results (benchmark v2: thread-verified labels)

**Sources:**
- Labels: [`data/benchmark/thread_annotations.json`](../data/benchmark/thread_annotations.json).
  Each label cites the diagnosing forum post with a verbatim quote. They
  were assigned by an LLM (Claude) and have **not yet been reviewed by a
  human**; see `data/benchmark/SPOT_CHECK.md`.
- Results: [`paper_eval_v2.json`](../data/benchmark/results/paper_eval_v2.json)
  and [`paper_eval_v2_explicit.json`](../data/benchmark/results/paper_eval_v2_explicit.json),
  both produced at commit `528f945` (clean tree).
- Command: `python training/paper_eval.py --ground-truth data/benchmark/ground_truth_real_v2.json --derived-dir data/benchmark/derived_v2`.

**Label audit**, from `registry_summary.json` → `v2_thread_verified`:
- Of the 55 logs previously called labelled, 24 have a cause stated in their
  thread: 11 confirm the old label and 13 change it.
- Cohen's kappa between the old and verified labels is **0.39**.
- 15 threads have no agreed cause.
- 7 logs are not failures (test flights, on-ground and post-crash logs), and
  1 is a Gazebo simulation.
- 8 logs could not be reviewed from the annotation environment.

**Evaluation set:** 22 logs from 21 incidents, 9 classes. Nine logs are
`mechanical_failure`. 7 labels are explicit and 15 tentative.

| Claim | Value | Status |
|---|---|---|
| Chance: random guess by label frequency | mean 0.100 (95th percentile 0.211) | Reproducible |
| Chance: always predict the majority class | 0.065 | Reproducible |
| RandomForest, windows split at random (leaky) | 0.991 ± 0.011 | Reproducible |
| RandomForest, grouped by log file | 0.106 ± 0.007 | Reproducible |
| **RandomForest, grouped by incident** | **0.052 ± 0.003**; ECE 0.100 | Reproducible |
| ExtraTrees, windows split at random (leaky) | 1.000 ± 0.000 | Reproducible |
| **ExtraTrees, grouped by incident** | **0.050 ± 0.001**; ECE 0.093 | Reproducible |
| Rule engine alone | 0.046 [0.000, 0.129]; 2/22 correct | Reproducible |
| Rules + fusion, CITA on / off | 0.000 (0/22 correct) / 0.028 (1/22) | Reproducible |
| Explicit-label subset (7 logs), rule engine | 1/7 correct; CITA on 0/7 | Reproducible |

**Reading these numbers:**
- **Leakage is larger with cleaner labels.** A random window split gives
  0.99–1.00, while incident grouping gives 0.05.
- **The rule engine names symptoms, not causes.** Of 9 verified sudden
  motor/ESC failures, it labels 4 as `power_instability` (current drops when
  a motor stops) and 2 as `motor_imbalance` (the controller compensates).
  With CITA on, 5 of 9 become `motor_imbalance`. So the engine labels the
  downstream symptom, not the failure.
- **No method beats chance** on the verified labels.

## Historical and retracted claims

| Claim | Value | Artifact | Command | Commit | Status |
|---|---|---|---|---|---|
| Grouped real-incident log Macro F1 (`v3_unambiguous`) | 0.500 on 23 incidents | missing from every branch and release | cannot be regenerated. Its 107-log pool (84 train / 23 test, per the cohort manifest) is larger than the 55 labelled real logs that exist, so it must have included simulated BASiC flights. Its F1 was also scored across all classes | not recorded | **Text-only, superseded** by the reproducible table above |
| Incident-level ECE (`v3_unambiguous`) | 0.153 | missing | as above | not recorded | **Text-only, superseded** |
| `v3_grouped` (rejected: contradictory labels) | 0.559 / 0.158 | missing | — | not recorded | Text-only, rejected |
| `v2_111` (filename grouping; leaky) | 0.670 / 0.069 | missing | — | not recorded | Text-only, leaky |
| ExtraTrees, 5 grouped seeds | 0.584 ± 0.025 F1, 0.167 ± 0.006 ECE | missing | `training/run_model_experiments.py` (inputs missing) | not recorded | **Text-only** |
| 45-log hybrid benchmark | Macro F1 0.14 | [`benchmark_results_hybrid.md`](../benchmark_results_hybrid.md) | `python -m src.cli.main benchmark` (after `git lfs pull`) | not recorded | Artifact present; ungrouped, uses pre-correction labels |
| 6-log "release" benchmark | Macro F1 0.81 | [`release_benchmark_results.md`](../release_benchmark_results.md) | — | — | **Retracted** as training-set score (C4) |
| BASiC "1.0 F1", "ECE 0.0001" | — | — | — | — | **Retracted** (C1) |
| `v4_improved` | 0.691 / 0.086 | cited report does not exist | — | — | **Retracted** (C7) |
| Triage time reduction | 84% / 98% | no raw records | — | — | **Retracted** (C3) |

## Runtime and engineering

| Claim | Value | Artifact | Command | Status |
|---|---|---|---|---|
| Runtime feature count | 111 finite features | `models/feature_columns.json`, `src/features/pipeline.py` | `python -m src.cli.main demo --format json` | Reproducible |
| Acceptance latency / memory figures | see README table | `benchmarks/acceptance.py` output (not committed) | `uv run --isolated --no-project --with numpy --with scipy --with pyarrow python benchmarks/acceptance.py` | Machine-dependent; re-measure before citing |
| Test suite | all pass in CI | CI run on the commit | `python -m pytest -q` | CI is authoritative; counts are not hard-coded |

## Why the historical figures remain "Text-only"

The full git history was fetched on 2026-09-25 (234 commits, all branches),
and the only release was checked.

**What exists:**
- `training/ece_report.json` at `65376f8` (the retracted BASiC figure),
  `cc72a71` (ECE 0.127 on 22 flights) and `6f0bc32` (ECE 0.042, target 1.0).
- The sealed real-only cohort manifest from branch `goal-loop-results`, now
  at `data/cohorts/cohort_manifest.json`.

**What was never committed anywhere:** `models/candidates/**`,
`training/candidates/**` and `data/ablation/ablation_report.json`.

Those runs cannot be regenerated. The reproducible real-log benchmark above
replaces them. Its inputs are recovered as follows:
- 43 logs via `git lfs pull`;
- 5 restored from git history;
- 3 re-downloaded.

All of these were checked against their recorded SHA256. Eight labelled logs
remain unrecoverable from this environment; they are listed in
`data/benchmark/registry_summary.json`.

## Next steps

1. Done for v2 (LLM-annotated, verifiable). Next, a human spot-check (`data/benchmark/SPOT_CHECK.md`) and the 8 unreviewed logs.
2. Recover the eight missing logs and add new incidents, aiming for 100 or
   more.
3. Freeze the protocol in `docs/PREREGISTRATION.md` before scoring a new
   holdout.
