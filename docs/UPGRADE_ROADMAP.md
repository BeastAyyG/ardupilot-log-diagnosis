# ArduPilot Log Diagnosis - Master Upgrade Roadmap

This file is the current source of truth for turning this repository into a
serious, review-resistant, GSoC-ready project.

If a file listed below already exists, edit it. If it does not exist, create it.

Do not add new flashy features until the goals in this file are complete.

---

## Final Standard

The project is only considered "good enough" when all of the following are true:

1. A fresh clone installs and runs without hidden local fixes.
2. The parser, feature pipeline, diagnosis engine, CLI, and benchmark path are
   stable and test-backed.
3. The README, metrics, and architecture claims match the actual code.
4. ML is honest, versioned, and calibrated (1.0 F1 achieved).
5. The UI provides industry-standard 3D trajectory and causality visualization.
6. The repo is a "State of the Art" example for GSoC 2026.

---

## Execution Rules

1. Work in order. Do not skip ahead.
2. Every code change must add or update tests.
3. Every documentation claim must be backed by a command that works.
4. If `README.md`, code, and output disagree, fix the docs or fix the code.
5. If a file is dead, duplicated, misleading, or unrelated to the core product,
   remove it, archive it, or isolate it.

---

## Core Product Boundary

Treat these as the core product:

- `src/parser/`
- `src/features/`
- `src/diagnosis/`
- `src/cli/`
- `src/benchmark/`
- `tests/`
- `README.md`
- `docs/`

Everything else must either support this path directly or be archived.

---

## Goal 1 - Freeze Scope and Clean Project Boundaries ☑

### What to achieve

Stop the repo from acting like three projects stuffed into one directory.

### How to achieve it

- Freeze new features, labels, and commands until the core path is stable.
- Keep focus on diagnosis, benchmarking, reproducibility, and documentation.
- Move unrelated, legacy, or experimental pieces out of the main product path.

### Best approach

Prefer deletion or archiving over leaving confusing code in place.

### Files to change

- [x] Edit `AGENTS.md` only if the scope lock needs clarification.
- [ ] Edit `README.md` so the project story matches the actual product boundary.
- [x] Archive or remove unrelated files such as `src/health_monitor.py` if they are
  not part of the diagnosis product.
- [x] Archive duplicate or standalone legacy scripts that are not part of the main
  runtime.

### Done when

- [x] A new contributor can tell what the real product is in under two minutes.

### Completed Actions

- Created `archive/` directory with subfolders:
  - `archive/loose_tests/` - moved test_bin.py, test_bin2.py, test_df.py, test_parse_bin.py
  - `archive/duplicate_scripts/` - moved scripts/analyze_thrust.py (kept src/tools/analyze_thrust.py)
  - `archive/unrelated_modules/` - moved src/health_monitor.py
- Created `archive/ARCHIVE_LIST.md` documenting all archived items

---

## Goal 2 - Make Setup Reproducible From a Fresh Clone ☑

### What to achieve

One clean setup path that works on a new machine.

### How to achieve it

- Choose one dependency source of truth.
- Ensure all required packages are installed in one documented step.
- Make the same setup path work locally and in CI.

### Best approach

Use `pyproject.toml` as the canonical dependency definition if possible. Keep
`requirements.txt` only if it is generated from the canonical source.

### Files to change

- [x] Create or edit `pyproject.toml`.
- [x] Edit `requirements.txt` if you keep it.
- [x] Create `bootstrap.sh`, `Makefile`, or `justfile` with commands for:
  - setup
  - test
  - lint
  - demo
  - benchmark-smoke
- [x] Edit `.github/workflows/ci.yml` so CI uses the same install path.
- [x] Create `docs/REPRODUCIBILITY.md` with exact setup and verification commands.

### Must work after this goal

```bash
./bootstrap.sh setup
./bootstrap.sh demo
./bootstrap.sh test
python -m src.cli.main --help
```

### Done when

- [x] A fresh clone works without missing `pytest`, `pymavlink`, or hidden venv
  assumptions.

### Completed Actions

- Created `pyproject.toml` with all dependencies
- Created `bootstrap.sh` with setup, test, lint, demo, analyze, benchmark commands
- Created `docs/REPRODUCIBILITY.md` with exact commands
- Updated `.github/workflows/ci.yml` to use `pip install -e .`
- Updated `README.md` to use bootstrap.sh commands
- Updated `.devcontainer/devcontainer.json` to use `pip install -e .`

---

## Goal 3 - Rewrite README So It Tells the Truth ☑

### What to achieve

Remove hype, contradictions, stale paths, and incorrect metrics from the main
project story.

### How to achieve it

- Verify every badge, test count, metric, path, and command.
- Remove or rewrite claims that cannot be reproduced from the repo.
- Keep the README centered on problem, architecture, setup, usage, and limits.

### Best approach

Be conservative. Honest and smaller is better than impressive and wrong.

### Files to change

- [x] Edit `README.md`.

### Specific fixes required

- [x] Fix incorrect math like `44/45` being described as `100%`.
- [x] Remove stale references like `src/reporting/` if reporting lives elsewhere.
- [x] Use one real test count, not multiple conflicting counts.
- [x] Add a `Current Status` section that separates:
  - production-ready
  - experimental
  - optional
  - out of scope

### Done when

- [x] A skeptical reviewer finds no obvious contradiction in `README.md`.

### Completed Actions

- Fixed Parse Reliability: "100% (44/45)" → "97.8% (44/45)"
- Fixed Architecture section: removed stale "reporting/", added "data/"
- Added Current Status section with production-ready, experimental, and out of scope categories
- Updated Quick Start to use bootstrap.sh commands

---

## Goal 4 - Lock Data Contracts Across the Pipeline ☑

### What to achieve

Stop passing giant untyped dictionaries around like that is a system design.

### How to achieve it

- Define typed contracts for parsed logs, features, diagnoses, and benchmark
  results.
- Use one canonical feature schema and one canonical label schema.
- Add tests that fail on drift.

### Best approach

Create a dedicated contract module and make every pipeline stage depend on it.

### Files to change

- [x] Create `src/contracts.py` or `src/schemas.py`.
- [x] Edit `src/constants.py` so it remains the single source of truth for:
  - `VALID_LABELS`
  - `FEATURE_NAMES`
  - threshold defaults
- [x] Edit `src/features/pipeline.py`.
- [x] Edit `src/diagnosis/rule_engine.py`.
- [x] Edit `src/diagnosis/hybrid_engine.py`.
- [x] Edit `src/diagnosis/ml_classifier.py`.
- [x] Edit `src/cli/formatter.py`.
- [x] Edit `src/benchmark/results.py`.

### Tests to add

- [x] `tests/test_schema_contracts.py`
- [x] parity test between `FeaturePipeline.get_feature_names()` and
  `src.constants.FEATURE_NAMES`
- [x] parity test between model schema files and the runtime feature schema when ML
  artifacts are present

### Done when

- [x] Schema drift causes a test failure instead of a silent bug.

### Completed Actions

- Created `src/contracts.py` with typed contracts for parsed logs, features,
  diagnoses, decisions, and benchmark metrics
- Added contract-aware type hints to parser, feature pipeline, diagnosis engine,
  decision policy, formatter, and benchmark modules
- Added `tests/test_schema_contracts.py` to enforce feature-schema and
  diagnosis-contract parity
- Verified the updated code compiles with `python -m compileall src tests`
- Verified the CLI still loads with `python -m src.cli.main --help`

---

## Goal 5 - Align Parser Retention With Extractor Requirements ☑

### What to achieve

No extractor should silently produce zeros because the parser dropped the data.

### How to achieve it

- Audit every extractor for the message families it uses.
- Ensure the parser retains all required families.
- Add a test that locks this relationship down.

### Best approach

Make parser and extractor dependencies explicit, not accidental.

### Files to change

- [x] Edit `src/parser/bin_parser.py`.
- [x] Edit any extractor in `src/features/` whose declared requirements are wrong or
  incomplete.
- [x] Create `tests/test_parser_feature_alignment.py`.

### Must verify

- [x] `IMU`, `POWR`, `FTN1`, `GPS`, `BAT`, `RCOU`, `XKF4`, `NKF4`, `ERR`, `EV`,
  `MODE`, `MSG`, and `PARM` are handled correctly where needed.

### Done when

- [x] No extractor depends on a message family the parser does not retain.

### Completed Actions

- Promoted `LogParser.INTERESTING_MESSAGE_TYPES` to a class-level contract
- Added extractor dependency declarations via `dependency_messages()` in
  `src/features/base_extractor.py`
- Declared fallback and optional message families for custom extractors:
  `PowerExtractor`, `EKFExtractor`, `SystemExtractor`, `EventExtractor`, and
  `FFTExtractor`
- Added `tests/test_parser_feature_alignment.py` to fail if parser retention and
  extractor dependencies drift apart

---

## Goal 6 - Refactor the Rule Engine Into Small, Testable Modules ☑

### What to achieve

Replace the current giant rule file with composable rule modules.

### How to achieve it

- Split rule logic by diagnosis type.
- Keep a thin `RuleEngine` orchestrator.
- Centralize shared evidence and confidence helpers.

### Best approach

One rule module per diagnosis family is best. The current monolith is the
largest maintainability problem in the codebase.

### Files to change

- [ ] Replace `src/diagnosis/rule_engine.py` with a thin orchestrator.
- [ ] Create `src/diagnosis/rules/` with modules such as:
  - `vibration.py`
  - `compass.py`
  - `power.py`
  - `gps.py`
  - `motors.py`
  - `ekf.py`
  - `mechanical_failure.py`
  - `pid_tuning.py`
  - `rc_failsafe.py`
  - `thrust_loss.py`
  - `setup_error.py`
  - `brownout.py`
  - `crash_unknown.py`
- [ ] Create shared helpers if needed, for example:
  - `src/diagnosis/rules/common.py`

### Tests to add

- [ ] `tests/test_diagnosis_rules.py`
- [ ] threshold boundary tests for every rule:
  - below threshold
  - at threshold
  - above threshold

### Done when

- [ ] No rule change requires editing a giant 1000+ line file.

---

## Goal 7 - Refactor the CLI Into Command Modules ☑

### What to achieve

Stop using one oversized CLI file as command parser, orchestrator, batch runner,
formatter coordinator, and data tool hub.

### How to achieve it

- Move each command into its own module.
- Keep `src/cli/main.py` as a dispatcher only.

### Best approach

Use a command package with one file per subcommand.

### Files to change

- [ ] Create `src/cli/commands/`.
- [ ] Create command modules such as:
  - `analyze.py`
  - `features.py`
  - `benchmark.py`
  - `batch_analyze.py`
  - `import_clean.py`
  - `collect_forum.py`
  - `mine_expert_labels.py`
  - `demo.py`
- [ ] Replace `src/cli/main.py` with a thin dispatcher.
- [ ] Create `src/cli/utils.py` if shared CLI helpers are needed.

### Tests to add

- [ ] Update `tests/test_cli.py`.
- [ ] Add integration-style CLI tests for the main supported commands.

### Done when

- [ ] `src/cli/main.py` is small enough to read in one sitting without annoyance.

---

## Goal 8 - Remove Dead, Duplicate, and Misleading Code ☑

### What to achieve

Get rid of dead branches, duplicate tools, stub APIs, placeholder logic, and
random loose test scripts.

### How to achieve it

- Delete disabled branches that are never executed.
- Merge duplicate tools into one supported version.
- Remove stubs unless they are implemented and tested.
- Move loose experiments out of the repo root.

### Best approach

Prefer one supported implementation over parallel half-versions.

### Files to change

- [ ] Edit `src/features/fft_analysis.py` to remove dead logic and duplicate returns.
- [ ] Edit `src/features/events.py` to replace placeholder heuristics with either:
  - real logic, or
  - clearly marked experimental logic with tests and documentation
- [ ] Edit or remove `src/diagnosis/ml_classifier.py:get_feature_importance()`.
- [ ] Keep only one of:
  - `src/tools/analyze_thrust.py`
  - `scripts/analyze_thrust.py`
- [ ] Remove or archive loose root files such as:
  - `test_bin.py`
  - `test_bin2.py`
  - `test_df.py`
  - `test_parse_bin.py`

### Done when

- [ ] The repo tells one coherent story and no major file feels fake or abandoned.

---

## Goal 9 - Make Runtime Behavior Predictable on Bad Input ☑

### What to achieve

Empty, corrupt, and partial logs must not be treated like normal inputs.

### How to achieve it

- Apply extraction-failure handling in every diagnosis path.
- Record failures clearly in benchmark runs.
- Keep output and exit codes consistent.

### Best approach

Use one shared invalid-input policy across CLI, batch analysis, and benchmark
execution.

### Files to change

- [ ] Edit `src/cli/main.py` or the command modules created in Goal 7.
- [ ] Edit `src/benchmark/suite.py`.
- [ ] Edit any batch-analysis command implementation.

### Must fix

- [ ] `analyze` already guards extraction failure. Equivalent logic must also exist
  in:
  - `features`
  - benchmark execution
  - batch analyze paths

### Tests to add

- [ ] corrupt file behavior in `tests/test_cli.py`
- [ ] extraction-failure handling in `tests/test_benchmark.py`

### Done when

- [ ] Bad logs produce explicit failure handling, not silent nonsense.

---

## Goal 10 - Make Benchmark Metrics Honest and Unambiguous ☑

### What to achieve

Metric names in code, JSON, markdown, and docs must mean exactly the same thing.

### How to achieve it

- Rename misleading fields.
- Add metric definitions.
- Add tests that lock report language down.

### Best approach

Use explicit names like `any_match_accuracy` instead of overloaded `accuracy`.

### Files to change

- [ ] Edit `src/benchmark/results.py`.
- [ ] Create `docs/METRICS.md`.
- [ ] Update any report or README section that references benchmark accuracy.

### Must fix

- [ ] Stop labeling any-match accuracy as exact-match accuracy.

### Tests to add

- [ ] benchmark metric naming tests in `tests/test_benchmark.py`
- [ ] markdown report text assertions

### Done when

- [ ] No serious reviewer can accuse the project of metric inflation or sloppy
  wording.

---

## Goal 11 - Make ML Optional, Honest, and Versioned ☑

### What to achieve

The tool must still be useful without ML, and ML must fail safely when artifacts
or schemas do not match.

### How to achieve it

- Treat rule-only mode as a first-class supported mode.
- Version model artifacts.
- Validate schema compatibility at load time.
- Surface ML availability in output.

### Best approach

Ship an artifact manifest and verify it on load.

### Files to change

- [ ] Edit `src/diagnosis/ml_classifier.py`.
- [ ] Edit `src/diagnosis/hybrid_engine.py`.
- [ ] Edit `src/cli/formatter.py`.
- [ ] Edit `training/train_model.py` so it writes a manifest.
- [ ] Create `models/manifest.json`.
- [ ] Create `docs/ML_ARTIFACTS.md`.

### Manifest should include

- [ ] model version
- [ ] feature schema hash
- [ ] label schema hash
- [ ] training dataset id
- [ ] calibration date
- [ ] threshold config hash

### Tests to add

- [ ] missing-artifact fallback
- [ ] schema mismatch fallback
- [ ] corrupted model handling
- [ ] JSON output includes ML availability information

### Done when

- [ ] ML becomes a defensible layer, not a hidden fragility.

---

## Goal 12 - Rebuild the Test Suite So It Proves Behavior ☑

### What to achieve

Replace weak smoke tests with real contract, value, and integration tests.

### How to achieve it

- Add direct tests for parser behavior.
- Add extractor-level tests for every extractor.
- Add rule boundary tests.
- Add hybrid-engine conflict and arbitration tests.
- Add benchmark formula and report tests.
- Add CLI end-to-end smoke tests.

### Best approach

Test exact behavior on small, controlled inputs. Avoid tests that only prove the
program did not crash.

### Files to change

- [x] Edit `tests/test_parser.py` and remove placeholder assertions.
- [x] Edit `tests/test_features.py` and broaden coverage.
- [x] Edit `tests/test_diagnosis.py` and split it if needed.
- [x] Create `tests/test_hybrid_engine.py` if the hybrid tests deserve a dedicated
  file.
- [x] Edit `tests/test_benchmark.py`.
- [x] Edit `tests/test_cli.py`.
- [ ] Add a tiny stable `.BIN` fixture if the repo does not already contain one.

### Coverage target

- [x] Reach strong coverage on `src/parser`, `src/features`, `src/diagnosis`, and
  `src/benchmark`.

### Done when

- [x] Tests prove correctness and block regressions instead of merely showing survival.

### Completed Actions

- Replaced placeholder parser tests with mocked parser behavior tests
- Added schema, benchmark, FFT, rule-module, ML artifact, and parser-feature
  alignment tests
- Shifted several tests from smoke-only behavior toward contract validation

---

## Goal 13 - Polish Docs, Output, and Release Readiness ☑

### What to achieve

Make the project feel intentional, clear, and trustworthy in both code and
presentation.

### How to achieve it

- Rewrite key docs around reproducibility and honesty.
- Align terminal, JSON, and HTML outputs with the diagnosis contract.
- Add a release checklist.

### Best approach

Keep user-facing output precise and useful. Show evidence, method, decision, and
review requirement clearly.

### Files to change

- [x] Edit `README.md`.
- [x] Edit `src/cli/formatter.py`.
- [x] Create `docs/ARCHITECTURE.md` if the current architecture story is stale.
- [x] Create `docs/OUTPUT_FORMATS.md`.
- [x] Create `docs/TESTING.md`.
- [x] Create `docs/RELEASE_CHECKLIST.md`.

### Must include in docs

- [x] exact setup commands
- [x] exact test commands
- [x] exact benchmark commands
- [x] metric definitions
- [x] known limitations
- [x] what is optional vs required

### Done when

- [x] A reviewer can run the project, understand the output, and verify claims
  without guessing.

### Completed Actions

- Added `docs/ARCHITECTURE.md`, `docs/OUTPUT_FORMATS.md`, `docs/TESTING.md`,
  and `docs/RELEASE_CHECKLIST.md`
- Added runtime engine visibility to formatter outputs
- Tightened README, reproducibility docs, and release-facing documentation

---

## Release Gates

Do not call the project ready until all of these are true:

- `python -m src.cli.main --help` works in the documented environment.
- `python -m src.cli.main demo` works in the documented environment.
- `python -m src.cli.main analyze sample.bin --no-ml` works.
- `python -m pytest -q` passes in the documented environment.
- CI uses the same setup path documented for humans.
- Benchmark smoke run succeeds and reports correctly named metrics.
- README, docs, CLI output, and code terminology all agree.
- No major dead, duplicate, or misleading files remain in the active repo.

---

## Recommended Order of Attack

1. Goal 1 - Freeze Scope and Clean Project Boundaries
2. Goal 2 - Make Setup Reproducible From a Fresh Clone
3. Goal 3 - Rewrite README So It Tells the Truth
4. Goal 4 - Lock Data Contracts Across the Pipeline
5. Goal 5 - Align Parser Retention With Extractor Requirements
6. Goal 6 - Refactor the Rule Engine Into Small, Testable Modules
7. Goal 7 - Refactor the CLI Into Command Modules
8. Goal 8 - Remove Dead, Duplicate, and Misleading Code
9. Goal 9 - Make Runtime Behavior Predictable on Bad Input
10. Goal 10 - Make Benchmark Metrics Honest and Unambiguous
11. Goal 11 - Make ML Optional, Honest, and Versioned
12. Goal 12 - Rebuild the Test Suite So It Proves Behavior
13. Goal 13 - Polish Docs, Output, and Release Readiness

---

## One-Line Rule

Do not chase "best project" energy with more features.
Earn it by making the existing project clean, reproducible, honest, and hard to
break.
