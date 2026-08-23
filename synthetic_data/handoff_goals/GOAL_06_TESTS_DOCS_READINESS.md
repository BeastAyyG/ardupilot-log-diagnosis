# Goal 06 — Integrate Tests, Documentation, and Readiness Evidence

## Current verification snapshot (2026-08-23)

- `ruff check synthetic_data training tests`: passed.
- Focused lifecycle/artifact/runtime safety regression: 27 passed.
- Full `pytest tests/ -q`: 607 passed with 14 third-party deprecation warnings.
- The previously failing active anomaly test now has an explicit 104-column
  sidecar recovered from the exact commit that introduced the current binary;
  it matches both that historical ordered runtime schema and the artifact scaler
  dimension. The binary itself was not changed.
- The formal source/dirty-snapshot receipt is generated and verifies against the
  current worktree. Real external evidence is still missing, so this snapshot
  is not release authorization.

## Copy/paste prompt

Integrate Goals 01–05, then make documentation match the code exactly. Run the
full suite and regenerate the source-bound readiness receipt after any edit. Do not turn missing
external evidence into a success claim. Keep the branch uncommitted unless the
integration owner explicitly authorizes a commit.

## Documentation to correct

- `synthetic_data/README.md`: replace old sim_vehicle/manual UDP instructions
  with the owned direct binary command using `--ardupilot-root`, `--binary`,
  exact `tcpin:127.0.0.1:14550`, and `--confirm-sitl`.
- Use “development test” rather than “release lockbox.” Explain that dose/model
  selection consumes it and a new blinded confirmation cohort is still required.
- Separate the small manifestation-predicate pilot from the later verification
  cohort. Freeze/hash predicates before verification.
- Document one parameter schema per frame/build, physical-flight verification,
  near-duplicate audit, candidate-directory training, calibration diagnostic,
  technical validator, evidence builder, trusted policy, and activation receipt.
- Update `synthetic_data/RESEARCH.md`, `docs/SYNTHETIC_DATA_IMPLEMENTATION.md`,
  `docs/PRODUCTION_READINESS.md`, and the root `README.md` command chain.
- Replace stale `synthetic_data/reports/READINESS.md` v1 claims with current
  schema evidence or an explicit “obsolete/evidence pending” notice.

## Verification

- Focused unit/integration suites for lab, dataset, split, trainer, validator,
  gate, activation, and tamper paths.
- Full `pytest tests/ -q`, ruff, JSON parse/schema checks, CLI `--help` smoke tests,
  and import tests without undeclared `jsonschema`.
- Compare any unexplained full-suite failure read-only against the main worktree.
- Record Python/platform/package versions, commands, code/dirty snapshot hashes,
  input/output hashes, exact test counts, and limitations.
- Use `python -m synthetic_data.readiness_receipt build`, followed immediately
  by `verify`; do not edit source after the build without regenerating it.

## Acceptance criteria

- A new user can follow documentation without parser errors or port conflicts.
- No documentation describes a development metric as production evidence.
- Readiness report is reproducible from exact inputs and does not cite stale v1
  split/fidelity/ablation artifacts.
- Final handoff lists branch, changed files, tests, failures, untracked files,
  missing external assets, and the statement: “No accuracy gain demonstrated”
  unless Goal 07 has genuinely passed.
