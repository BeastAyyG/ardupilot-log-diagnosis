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

## Model performance

| Claim | Value | Artifact | Command | Commit | Status |
|---|---|---|---|---|---|
| Grouped real-incident log Macro F1 (`v3_unambiguous`) | 0.500 on 23 incidents | missing (`training/candidates/` absent) | to be restored: `training/paper_eval.py` (planned) | not recorded | **Text-only** |
| Incident-level ECE (`v3_unambiguous`) | 0.153 | missing | as above | not recorded | **Text-only** |
| `v3_grouped` (rejected: contradictory labels) | 0.559 / 0.158 | missing | — | not recorded | Text-only, rejected |
| `v2_111` (filename grouping; leaky) | 0.670 / 0.069 | missing | — | not recorded | Text-only, leaky |
| ExtraTrees, 5 grouped seeds | 0.584 ± 0.025 F1, 0.167 ± 0.006 ECE | missing | `training/run_model_experiments.py` (inputs missing) | not recorded | **Text-only** |
| 45-log hybrid benchmark | Macro F1 0.14 | [`benchmark_results_hybrid.md`](../benchmark_results_hybrid.md) | `python -m src.cli.main benchmark` (logs are Git LFS stubs in this checkout) | not recorded | Artifact present; inputs missing |
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

## Why the headline figures are "Text-only"

Three problems stop the 0.500 / 0.153 figure from being regenerated today:
- **Shallow clone.** The repository is a shallow clone (history starts at
  `2816a63`, 2026-08-25), so the commits that produced these runs are not
  reachable.
- **Missing logs.** The real forum logs are Git LFS pointers in
  `data/kaggle_backups/` and absent elsewhere.
- **Missing lineage columns.** `training/groups.csv` has only a `source_log`
  column, with no `source_url` or `source_type`.

## Planned fixes

1. `git fetch --unshallow` and record the producing commits here.
2. Restore the real logs locally in a git-ignored directory.
3. Rebuild the training matrices with `incident_id`, `source_url` and
   `source_type` columns.
4. Add `training/paper_eval.py`. It writes one JSON per run containing the
   commit, data hash, seed, metrics and bootstrap confidence intervals.
5. Update each row above to **Reproducible**, or retract it.
