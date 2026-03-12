# Release Checklist

- [x] `./bootstrap.sh setup` works in a fresh clone
- [x] `python -m src.cli.main --help` works
- [x] `./bootstrap.sh demo` works
- [x] `./bootstrap.sh test` passes
- [x] benchmark report uses `Any-Match Accuracy`, `Top-1 Accuracy`, and `Exact-Match Accuracy`
- [x] `README.md` matches the current code and commands
- [x] `docs/METRICS.md` matches benchmark output
- [x] ML artifacts include `models/manifest.json`
- [x] invalid or corrupt logs fail safely
- [x] archived code is not referenced by the active runtime
