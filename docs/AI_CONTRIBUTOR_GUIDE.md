# AI contributor guide

This repository is an ArduPilot log-analysis system. AI agents may improve
the code, tests, and documentation, but must preserve the diagnostic safety
boundaries below.

## Source of truth

- Runtime behavior: `src/`
- Public API contract: `src/web/schemas.py` and `src/web/app.py`
- Capability status: `src/parser/capabilities.py`
- Training contract: `training/data_contract.py`, `training/train_model.py`,
  and `training/validate_artifact.py`
- Release decision: `docs/PRODUCTION_READINESS.md`
- Model limitations: `docs/model_card.md`

If a README claim conflicts with a capability registry, test, model manifest,
or production-readiness report, update the documentation and code together;
never hide the stricter runtime behavior.

## Non-negotiable safety rules

1. Never invent a diagnosis, label, log, expert opinion, or metric.
2. Never train on a forum/search hypothesis without a source URL, log hash,
   incident/group identifier, and human-review status.
3. Keep all windows from one flight in the same evaluation split. Do not use
   filename-only grouping or column-order label fallbacks.
4. Do not promote an artifact unless grouped log Macro F1 is at least 0.70,
   incident ECE is at most 0.08, there are at least 50 independent holdout
   incidents, the feature schema matches, and the artifact validator passes.
5. A low-quality, generic-format, review-only, or experimental result must be
   marked as such and must require human review. It must not be presented as a
   confirmed root cause or flight-safety decision.
6. Do not change aircraft parameters or issue autonomous maintenance/flight
   commands. The system is a diagnostic aid.

## Standard workflow

1. Read this guide, `docs/PRODUCTION_READINESS.md`, and the relevant module
   tests before editing.
2. Make the smallest coherent code/documentation change. Add a regression
   test for every bug or contract change.
3. Run the focused tests, then the complete suite:

   ```powershell
   .venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
   .venv\Scripts\python.exe -m ruff check src tests training
   .venv\Scripts\python.exe -m compileall -q src training temporal-layer llm-orchestrator
   .venv\Scripts\python.exe -m pip check
   git diff --check
   ```

4. For release-facing work, run `tests/run_integration_check.py` and verify
   `/healthz`, `/readyz`, `/metrics`, `/api/capabilities`, and a real
   `/api/analyze` request.
5. Record changed metrics and known limitations in the production-readiness
   report and model card.

## Data acquisition and model work

Downloaded logs belong in a provenance-preserving raw pool, not directly in
the training set. Inspect payload signatures before trusting file extensions;
HTML download pages, malformed files, and unconfirmed topic hypotheses stay
out of training. A human reviewer must assign the final label and rationale.

Training experiments must write to a candidate directory and must never
overwrite `models/`. Promotion is a separate, reviewable operation. If the
release gates fail, keep the existing rules/legacy compatibility behavior and
say so explicitly.

## Commit and repository hygiene

Commit source, tests, and durable documentation. Do not commit local virtual
environments, pytest scratch directories, downloaded raw logs, secrets,
temporary experiment scripts, or generated model artifacts unless a documented
manifest explicitly requires them. Before pushing, inspect `git diff --cached`
and `git status` so provenance data and machine-local files are not accidentally
published.
