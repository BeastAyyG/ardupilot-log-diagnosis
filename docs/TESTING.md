# Testing

## Main Commands

```bash
./bootstrap.sh test
./bootstrap.sh demo
python -m src.cli.main --help
```

## Test Layers

- Unit tests in `tests/` cover parser, features, diagnosis rules, benchmark metrics, and formatter behavior.
- Contract tests validate feature schema and diagnosis structure.
- CLI smoke tests cover command dispatch and demo output.
- Compile checks are useful when dependency-heavy runtime tests are unavailable:

```bash
python -m compileall src tests training
```

## Current Gaps

- A stable, parseable sample `.BIN` fixture should replace the current weak sample path.
- Full end-to-end runtime verification still depends on local availability of ArduPilot log fixtures.
