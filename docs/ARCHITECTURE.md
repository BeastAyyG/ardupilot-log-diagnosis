# Architecture

## Runtime Path

The main diagnosis flow is:

`.BIN -> LogParser -> FeaturePipeline -> RuleEngine / HybridEngine -> Decision Policy -> Formatter`

## Module Ownership

- `src/parser/` - DataFlash `.BIN` parsing and metadata extraction
- `src/features/` - telemetry feature extraction
- `src/diagnosis/` - rule engine, ML classifier, hybrid fusion, decision policy
- `src/cli/` - user-facing command entrypoints and formatters
- `src/benchmark/` - benchmark execution and metrics reporting
- `src/data/` - clean import and forum collection utilities

## Rule Engine Layout

The rule engine is split into **one module per rule** (Milestone 3), so that no
rule change requires editing a file longer than 200 lines:

- `src/diagnosis/rules/compass.py` — `check_compass`
- `src/diagnosis/rules/crash_unknown.py` — `check_events`
- `src/diagnosis/rules/ekf.py` — `check_ekf`
- `src/diagnosis/rules/gps.py` — `check_gps`
- `src/diagnosis/rules/mechanical_failure.py` — `check_mechanical_failure`
- `src/diagnosis/rules/motors.py` — `check_motors`
- `src/diagnosis/rules/pid_tuning.py` — `check_pid_tuning`
- `src/diagnosis/rules/power.py` — `check_power`
- `src/diagnosis/rules/rc_failsafe.py` — `check_rc_failsafe`
- `src/diagnosis/rules/setup_error.py` — `check_setup_error`
- `src/diagnosis/rules/system.py` — `check_system`
- `src/diagnosis/rules/thrust_loss.py` — `check_thrust_loss`
- `src/diagnosis/rules/vibration.py` — `check_vibration`

`src/diagnosis/rules/__init__.py` re-exports the full catalogue, and
`src/diagnosis/rule_engine.py` is the orchestrator only. There is no `brownout`
module: brownout is emitted by `power.py`, which chooses between
`power_instability` and `brownout` based on which evidence branch fires.

The label set each module can emit is asserted against
`src/diagnosis/rules/` by `tests/test_label_coverage.py`; the per-rule
threshold boundaries are pinned by `tests/test_diagnosis_rules.py`.

## CLI Layout

`src/cli/main.py` is a dispatcher.

Command logic lives in:

- `src/cli/commands/analyze.py`
- `src/cli/commands/features.py`
- `src/cli/commands/benchmark.py`
- `src/cli/commands/batch.py`
- `src/cli/commands/demo.py`
- `src/cli/commands/import_clean.py`
- `src/cli/commands/collect_forum.py`
- `src/cli/commands/mine_expert_labels.py`
- `src/cli/commands/label.py`
