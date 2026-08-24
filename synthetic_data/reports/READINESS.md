# Synthetic Data Code-Readiness Receipt

The historical v1 metric report has been removed because it described obsolete
split, fidelity, and ablation inputs. Do not recover or cite those numbers as
current evidence.

The current machine-readable receipt is generated at
`synthetic_data/reports/readiness_receipt.json` with:

```powershell
D:/logdiagnosis/.venv/Scripts/python.exe -m synthetic_data.readiness_receipt build --root D:/logdiagnosis-codex --output D:/logdiagnosis-codex/synthetic_data/reports/readiness_receipt.json
D:/logdiagnosis/.venv/Scripts/python.exe -m synthetic_data.readiness_receipt verify --root D:/logdiagnosis-codex --output D:/logdiagnosis-codex/synthetic_data/reports/readiness_receipt.json
```

The receipt binds the exact HEAD, branch, Git index entries, current bytes or
missing state of every tracked file, every non-ignored untracked file, recursive
submodule state, and filtered porcelain status. Its own path is the sole
recorded exclusion to avoid self-hash recursion. It also records exact command
arguments, exit codes, output hashes/tails, JSON syntax validation, Python and
package versions, and explicit limitations.

This is a non-promoting code-readiness record. It cannot establish simulator
execution, physical calibration, OOD performance, blinded confirmation, an
independent release decision, or improved accuracy. Until those external facts
exist: **No accuracy gain demonstrated.**
