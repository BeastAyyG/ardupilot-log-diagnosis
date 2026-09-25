# Archive List

This file documents files and modules that have been moved out of the main product path.

## Reason

These files were archived because they were:
- Loose test files in the repo root (not in `tests/`)
- Duplicate implementations of tools that exist elsewhere
- Unrelated modules not part of the diagnosis product

## Archived Items

### Loose Test Scripts (→ archive/loose_tests/)

| File | Original Location | Reason |
|------|-------------------|--------|
| `test_bin.py` | repo root | Duplicate of proper tests in `tests/` |
| `test_bin2.py` | repo root | Duplicate of proper tests in `tests/` |
| `test_df.py` | repo root | Duplicate of proper tests in `tests/` |
| `test_parse_bin.py` | repo root | Duplicate of proper tests in `tests/` |

### Duplicate Scripts (→ archive/duplicate_scripts/)

| File | Original Location | Kept Version |
|------|-------------------|--------------|
| `analyze_thrust.py` | `scripts/analyze_thrust.py` | `src/tools/analyze_thrust.py` |

### Unrelated Modules (→ archive/unrelated_modules/)

| File | Original Location | Reason |
|------|-------------------|--------|
| `health_monitor.py` | `src/health_monitor.py` | Companion health monitor, not part of diagnosis product |

## How to Restore

If any archived item is needed, move it back from the archive folder to its original location.

## Archive Maintenance

- Review the archive folder periodically.
- Delete items that are confirmed to be no longer needed.
- Do not add new code to archived items.

### Unverified or retracted documents (→ archive/docs_unverified/), 2026-09-25

Each file carries a "HISTORICAL — UNVERIFIED" banner. Their claims are
explained in [CORRECTIONS.md](../CORRECTIONS.md).

| File | Reason |
|------|--------|
| `TRIAGE_STUDY_2026-03-02.md`, `MAINTAINER_TRIAGE_REDUX.md` | Triage-time claims with no raw records (C3) |
| `WILD_HOLDOUT_TEST_2026-03-01.md` | "Holdout" log later used for tuning and training (C5) |
| `CHANGELOG_2026-03-01.md` | Per-label F1 1.0 on ungrouped data; records the re-tuning behind C5 |
| `FORUM_ANNOUNCEMENT.md`, `FORUM_POST_DRAFT.md`, `MENTOR_QA_PREP.md` | Repeat retracted figures |
| `progress_showcase.md`, `progress_showcase_lockbox.md` | 2-log "holdout" showcases |

### Stale planning and hand-off documents (→ archive/docs_stale/), 2026-09-25

`SESSION_RESUME.md`, `PLAN.md`, `PLAN-gsoc-architecture.md`,
`gsoc_attack_plan.md`, `GSOC_SITL_BLUEPRINT.md`, `ML_STRATEGY_BLUEPRINT.md`,
`DEEP_PROGRAM_UNDERSTANDING.md`, `progress_timeline_2026-02-23.md`,
`data_request_pack_2026-02-23.md`, `ai_handoff/`,
`synthetic_data_handoff_goals/`, `gsoc_backup/` and `ENHANCEMENT_ROADMAP.md`
(a pasted AI chat). Personal dotfiles that were in `docs/gsoc_backup/` were
deleted. They remain in git history.
