# Current Synthetic-Data Handoff — 2026-08-23

Give this file and the linked numbered goal to the next coding AI. Work only in
`D:/logdiagnosis-codex` on `codex/session`. Do not commit, merge, push, release,
or edit `D:/logdiagnosis` without the integration owner's authorization.

## Evidence-backed progress in this continuation

1. OOD evidence production is implemented in `synthetic_data/ood.py`.
   It recomputes frozen-threshold lineage AUROC, detection at 5% ID FPR, ID FPR,
   per-domain detection/support, stratified bootstrap intervals, threshold
   reproduction, duplicate isolation, and detected-record runtime routing.
2. `synthetic_data/gate_advanced.py` now fails closed unless the OOD report has
   all four preregistered domains, enough support, exact ledger/design/threshold
   hashes, a reproduced threshold, and an end-to-end configured runtime route.
3. Development ablation writes a deterministic per-lineage prediction ledger
   through `synthetic_data/ablation_ledger.py`; a validator checks its report,
   dataset, class, seed, arm, lineage, target, and probability bindings.
4. Training and calibration diagnostics now produce detailed positive/negative
   independent real-lineage support for every class, compact gate-compatible
   per-class support, and a canonical calibration-method configuration hash.
   Artifact validation recomputes them before joblib deserialization and checks
   the serialized classifier copy afterwards.
5. The active anomaly binary's exact 104-column training schema was recovered
   from commit `f5e8a0749c985d0fa8c9684d8c3ca0f4801a6af6` and restored as
   `models/anomaly_feature_columns.json`. It equals the first 104 current runtime
   features and matches `scaler.n_features_in_`; the binary was not modified.
6. Feature fidelity now produces conditional linear/nonlinear C2ST, a
   familywise lineage-permutation p-value, conditional RBF MMD, balanced
   real-real envelopes, and simultaneous worst-stratum lineage-bootstrap
   bounds.
7. Raw temporal fidelity production is implemented end-to-end: frozen
   DataFlash channel extraction, raw-log/path/hash/provenance validation,
   cadence/jitter/dropout/missingness, ACF, PSD, coherence, lag/correlation,
   transition timing, simultaneous lineage bounds, feature-report integration,
   and fail-closed acceptance validation. Real bound logs are still absent.
8. Blinded physical-confirmation evidence now has a separate schema-valid
   cohort manifest, candidate/baseline prediction ledger, deterministic metric
   producer, and exact report validator. It rejects development overlap by
   lineage, raw artifact, and near-duplicate cluster; recomputes absolute and
   paired Macro-F1 intervals and simultaneous per-class recall bounds; and is
   required by the common evidence envelope. Real confirmation flights and an
   independent authority remain absent.
9. Production model selection is now invariant to exact repeated windows.
   Cross-validation folds are allocated from unique group/class representatives;
   exact feature/target/evaluation-unit copies are removed before feature
   selection, scaling, and fitting; weights are recomputed from canonical
   source-group/lineage rows with total mass tied to independent lineages. The
   manifest and classifier carry three exact method contracts, and validation
   checks them before and after deserialization.
10. The full candidate lifecycle now has a clean subprocess integration proof:
    freeze-split → real XGBoost train → measure_ece → validate_artifact → inert
    candidate → receipt present but untrusted → externally pinned authorized
    runtime. Sparse cohorts use a deterministic four-candidate search, medium
    cohorts 16, and cohorts with at least 64 independent training lineages use
    all 64; the exact design and hash are manifest/classifier-bound. The test
    gate and authority are explicitly fixture-only and do not establish an
    accuracy or release claim.
11. The unsafe-deserialization boundary is now systematic: calibration and
    optional acceptance envelopes are checked before `joblib.load`, and a
    mutation matrix proves altered manifest, artifact/input hashes, inference
    window, evaluation/search contracts, calibration schema/threshold, and
    incomplete acceptance inputs cannot trigger model loading. Runtime tests
    additionally prove future manifest, gate, and receipt schemas fail before
    deserialization.
12. `synthetic_data.readiness_receipt` now produces and verifies a strict,
    non-promoting code-readiness receipt. It binds HEAD, branch, Git index
    entries, current tracked bytes/deletions, every non-ignored untracked file,
    recursive submodule state, filtered status, command output hashes/tails,
    JSON syntax checks, runtime/package versions, and limitations. Only the
    receipt path is excluded to prevent self-hash recursion. Ten tamper tests
    cover tracked, untracked, staged-only, deleted, claim, content, failed-command,
    future-schema, uninitialized-gitlink, and ignored-runtime-state behavior.
13. Goal 02's remaining local isolation and failure-path gaps are closed. The
    execute CLI re-enters a fresh Linux user/network namespace, raises only
    `lo`, and binds actual parent/child namespace IDs, interface inventory,
    loopback state, and the `unshare` binary hash into receipt v4. The owned
    runner refuses direct/unfenced starts; collection rejects incomplete or
    same-namespace proof. Tests also cover early SITL exit, changing logger
    output, SIGKILL escalation, foreign MAVLink sources, and canonical-log
    rollback when final receipt publication fails.

## Verification run

```text
D:/logdiagnosis/.venv/Scripts/python.exe -m ruff check synthetic_data training tests
Result: passed

Focused lifecycle/artifact/runtime safety selection
Result: 27 passed, 38.14 seconds

D:/logdiagnosis/.venv/Scripts/python.exe -m pytest tests/ -q
Result: 607 passed, 14 dependency deprecation warnings (recorded in the exact
dirty-snapshot receipt)

D:/logdiagnosis/.venv/Scripts/python.exe -m synthetic_data.readiness_receipt verify --root D:/logdiagnosis-codex --output D:/logdiagnosis-codex/synthetic_data/reports/readiness_receipt.json
Result: passed
```

Focused tamper/failure tests cover missing OOD domains, near-duplicate leakage,
broken OOD runtime routing, prediction-ledger mutation, deterministic prediction
serialization, calibration-lineage manifest tampering, raw-log path traversal,
payload/provenance mismatch, temporal under-support, changed cadence, manual
temporal pass flags, and exact-report tampering.
Confirmation-specific tests additionally cover reused development lineages,
artifact/near-duplicate leakage, missing probability classes, edited utility
metrics, inadequate bootstrap draws, manual-metric substitution, and exact
report reproduction.
Model-selection tests copy one window 25 times and require identical fold unit
sets, per-lineage weight mass, selected hyperparameters, CV Macro-F1, and fitted
probabilities. Training-contract tampering must fail before deserialization.
Calibration-envelope, acceptance-input, and unknown future authorization-schema
tampering must also fail without calling `joblib.load`.
The clean lifecycle additionally proves that technical validation remains
non-promoting, a receipt without an external trust pin remains inert, and only
the exact pinned receipt enables the schema-v3 runtime.

## Still missing — do not convert these to claims

- No pinned Linux/WSL ArduPilot execution was available for one current-schema
  end-to-end pair. The early-exit/SIGKILL/logger/network-namespace paths now have
  fail-closed unit coverage but still require that real integration proof.
- No verified synthetic corpus has been collected by this laboratory.
- No real candidate-bound OOD prediction ledger or exercised end-to-end OOD
  runtime route exists; only the producer and tests exist.
- No policy-minimum physical calibration set (20 independent lineages/class)
  exists.
- No real blinded physical confirmation cohort, populated independently sealed
  prediction ledger, or independent release authority exists. The producer and
  fail-closed consumers now exist, but cannot create those external facts.
- Development prediction evidence cannot be reused as confirmation evidence.
- **No accuracy gain is demonstrated.**

## Best next prompts

### If Linux/WSL plus a pinned ArduPilot binary is available

Use [Goal 02](GOAL_02_COMPLETE_OWNED_SITL.md). Produce one healthy/intervention
pair, exercise all early-exit/logger/fencing paths, run collection, and report
the exact receipt/log hashes. Do not weaken isolation or accept manual launches.

### If real flight/OOD lineages are available

Use [Goal 04](GOAL_04_FIDELITY_AND_OOD.md). Freeze the OOD design before scoring,
extract the raw temporal ledger, populate all required OOD domains, exercise the
actual runtime abstention/rules path, and run the fidelity/OOD/gate commands.
Never hand-enter gate booleans.

### If only code and tests are available

Re-run [Goal 06](GOAL_06_TESTS_DOCS_READINESS.md) only after changing source so
the dirty-snapshot receipt stays exact. Goal 03's local safety barrier is
implemented; its remaining acceptance evidence requires real physical lineages.
Keep all results non-promoting without external authority and physical evidence.

## Integration handoff

- Branch: `codex/session`
- Commit created: no
- Worktree: dirty, with many pre-existing modified/untracked files; preserve all
  of them and inspect `git status --short` before writing.
- Integration owner must review and decide whether to commit or transfer changes.
