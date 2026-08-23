# Synthetic Data Lab: AI Handoff Goals

Use these files as copy/paste task briefs for another coding AI. They are ordered
to minimize repeated work and token use. Assign **one writing agent at a time**
to `D:/logdiagnosis-codex`; read-only reviewers may work concurrently.

Start with the dated [current handoff](CURRENT_HANDOFF_2026-08-23.md), then open
only the numbered goal matching the external assets available to the next AI.

## Non-negotiable workspace rules

- Antigravity owns `D:/logdiagnosis` on `main`. Never edit that worktree.
- Codex work belongs only in `D:/logdiagnosis-codex` on `codex/session`.
- Read `D:/logdiagnosis/AGENTS.md` and
  `D:/logdiagnosis/.harness/session.json` before writing.
- Check `git status --short` before every writing session.
- Do not commit, push, merge, rebase, release, delete worktrees, or edit shared
  dependency/lock manifests without an explicit integration-owner handoff.
- Use `D:/logdiagnosis/.venv/Scripts/python.exe` for tests on this machine.
- Preserve the central scientific rule: synthetic data may train a candidate,
  but calibration, threshold selection, development evaluation, and final
  confirmation must use independent real physical-flight lineages.
- Never claim an accuracy gain until a new blinded physical confirmation cohort
  passes the preregistered gates.

## Recommended order

1. [Goal 01 — Stabilize the branch](GOAL_01_STABILIZE_CURRENT_BRANCH.md)
2. [Goal 02 — Complete owned SITL execution](GOAL_02_COMPLETE_OWNED_SITL.md)
3. [Goal 03 — Complete model validation](GOAL_03_MODEL_VALIDATION.md)
4. [Goal 04 — Implement fidelity and OOD evidence](GOAL_04_FIDELITY_AND_OOD.md)
5. [Goal 05 — Build sealed acceptance evidence](GOAL_05_ACCEPTANCE_EVIDENCE.md)
6. [Goal 06 — Tests, documentation, and readiness receipt](GOAL_06_TESTS_DOCS_READINESS.md)
7. [Goal 07 — Run the real experiment](GOAL_07_REAL_EXPERIMENT.md)

Goals 02 and 03 may proceed in parallel only in separate isolated worktrees.
Goals 04 and 05 depend on their output contracts. Goal 06 integrates everything.
Goal 07 requires ArduPilot binaries/logs and real flight evidence that are not
present in this repository.

## Current truth

- The isolated `synthetic_data/` laboratory and schema-v3 model candidate path
  are substantially implemented.
- On 2026-08-23, `ruff check synthetic_data training tests` passed, the focused
  lifecycle/artifact/runtime safety regression passed **27 tests**, and
  the full `pytest tests/ -q` suite passed **607 tests** (14 dependency deprecation
  warnings). These results cover the current dirty `codex/session` worktree;
  they are not a release receipt.
- The machine-readable code-readiness receipt binds that verification to the
  exact dirty source state and verifies successfully. It is non-promoting and
  deliberately separate from physical evidence and release authority.
- No current-schema end-to-end ArduPilot SITL receipt has been produced.
- The current direct command still uses native RC UDP port 5501, which pinned
  ArduPilot binds on `0.0.0.0`; treat “loopback-only” as unproven until Goal 02
  disables/fences that port and receipts the isolation proof.
- No verified synthetic corpus has been collected with this laboratory.
- The OOD metric/routing producer and fail-closed gate consumer are implemented,
  but no real candidate-bound OOD prediction ledger has been collected.
- Development ablation predictions, per-class calibration lineage support, and
  the separate fail-closed blinded-confirmation ledger/report producer are now
  persisted or implemented and hash-bound. Real populated confirmation evidence
  and policy-minimum physical calibration support remain absent.
- No blinded physical confirmation cohort has been evaluated.
- Therefore, **no real-world accuracy improvement is demonstrated**.

Every AI handoff must report: branch, exact changed paths, commands/tests and
results, remaining failures, uncommitted/untracked files, and whether any claim
is evidence-backed or still blocked.
