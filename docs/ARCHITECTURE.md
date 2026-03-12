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

The rule engine is split into grouped rule modules:

- `src/diagnosis/rules/sensors.py`
- `src/diagnosis/rules/mechanics.py`
- `src/diagnosis/rules/power_and_system.py`
- `src/diagnosis/rules/control_and_events.py`

`src/diagnosis/rule_engine.py` is now the orchestrator only.

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
