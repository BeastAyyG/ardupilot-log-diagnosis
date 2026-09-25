# Goal 01 — Stabilize the Current Branch

## Copy/paste prompt

You are the stabilization owner for the synthetic-data work in
`D:/logdiagnosis-codex` on branch `codex/session`. Read `AGENTS.md`, the master
handoff README, and current `git diff` before acting. Do not edit
`D:/logdiagnosis`, shared manifests, or lockfiles. Finish the in-progress edits,
make every changed Python/JSON contract internally consistent, keep source files
under 500 lines, run focused tests, then run the broadest affordable regression
suite. Do not add features or claim accuracy. Return an evidence-based handoff.

## Immediate inspection targets

- `synthetic_data/collector.py`: the new strict DataFlash step-trajectory check
  was the last edit. Verify baseline → requested value → no reset semantics and
  add fault-path unit tests.
- `synthetic_data/planner.py`: manifest v3 now carries fixed simulation start,
  frame-specific schemas, injection baselines, and an empty automatic-change
  allowlist. Verify paired/unpaired plans and fingerprints.
- `synthetic_data/schemas/experiment_manifest.schema.json`: validate every
  generated scenario against the expanded schema.
- `synthetic_data/schemas/execution_receipt.schema.json`: receipt semantics were
  bumped to v4. Verify all real and fake receipt producers/consumers match.
- `training/validate_artifact.py` plus `training/artifact_validation_*.py`: run
  the new recomputation tests and inspect pre-deserialization failure behavior.
- Files over 500 lines currently include at least `synthetic_data/collector.py`,
  `training/train_model.py`, and `tests/test_synthetic_lab.py`; split them by
  responsibility without weakening tests.

## Required checks

```powershell
$py = 'D:/logdiagnosis/.venv/Scripts/python.exe'
& $py -m py_compile synthetic_data/*.py training/*.py src/diagnosis/*.py
& $py -m ruff format --check synthetic_data training src/diagnosis tests
& $py -m ruff check synthetic_data training src/diagnosis tests
& $py -m pytest tests/test_synthetic_lab.py tests/test_sitl_data_factory.py tests/test_artifact_validator.py tests/test_merge_datasets.py tests/test_training_data_contract.py tests/test_training_integrity.py tests/test_ml_artifacts.py -q
```

Then run `python -m pytest tests/ -q`. If a failure also occurs unchanged on
`D:/logdiagnosis` main, prove that with a read-only check and label it pre-existing.

## Acceptance criteria

- Python compiles; all JSON files parse; all laboratory schemas validate their
  generated fixtures.
- Ruff passes on changed files.
- Focused tests pass with new failure-path coverage.
- Every changed source file is under 500 lines.
- No writes occurred in the Antigravity worktree.
- Handoff lists exact remaining full-suite failures instead of hiding them.
