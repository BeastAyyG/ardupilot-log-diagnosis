# Goal 03 — Complete Model Candidate Validation and Activation

## Copy/paste prompt

Finish the schema-v3 train → calibration diagnostic → technical validation →
independently authorized activation chain. Work in `D:/logdiagnosis-codex` only.
Treat all joblib files as unsafe until hashes, inputs, split ledger, provenance,
and partition identities are verified. Development evaluation never authorizes
release. Implement tests before claiming the chain works.

## Existing implementation

- Training requires a hash-bound dataset report and frozen split ledger.
- Real partitions require at least 2 train, 2 calibration, and 1 development
  lineage per declared class; sparse classes are `real_unassigned`.
- Synthetic rows train only after verification and may not descend from
  calibration/development lineages.
- Hyperparameter search fits preprocessing inside grouped folds and scores
  maximum-window incident units.
- Grouped folds are built from unique group/class representatives, exact
  feature/target/evaluation-unit copies are removed before all preprocessing,
  and fit weights are recomputed from canonical source-group/lineage rows with
  total mass normalized to independent lineages. Tests prove that copying one
  window 25 times leaves folds, weight mass, best parameters, CV score, and
  fitted probabilities unchanged.
- Hyperparameter breadth is deterministically lineage-budgeted (4 candidates
  below 16 training lineages, 16 below 64, otherwise 64). The full design and
  hash are persisted in the manifest and classifier and recomputed by artifact
  validation.
- Calibration uses real calibration lineages only.
- Candidate output defaults outside active `models/` and is non-promoting.
- `training/validate_artifact.py` now recomputes partitions and incident metrics,
  verifies calibration report hashes, enforces thresholds, and can recompute an
  acceptance gate under a trusted policy hash.
- Runtime schema-v3 activation requires gate and promotion receipts.
- Development ablation now writes a deterministic, sorted, data/split/seed-bound
  prediction ledger with one target and probability vector per real lineage and
  arm. Its consumer rejects report-hash, class, seed, arm, lineage, and
  probability inconsistencies.
- Training, calibration diagnostics, and validation now produce and recompute
  positive/negative real calibration-lineage support for every declared class,
  bind the exact Platt-calibration method configuration hash, and reject
  tampering before model deserialization.
- `synthetic_data.confirmation` now validates a separately frozen physical
  cohort and candidate/baseline prediction ledger, rejects any development
  lineage/artifact/near-duplicate reuse, and deterministically recomputes the
  absolute and paired Macro-F1 intervals plus simultaneous per-class recall
  bounds. The acceptance envelope requires this embedded computed report.
- A clean subprocess integration test now executes freeze-split → train →
  measure_ece → validate_artifact → inactive candidate → untrusted receipt →
  externally pinned authorized runtime using the real CLIs and real XGBoost
  serialization. Its gate and authority are explicitly fixture-only and make
  no accuracy claim.
- Candidate-controlled manifest, input, split, training-design, calibration,
  and optional acceptance envelopes are all validated before `joblib.load`.
  A mutation matrix spies on deserialization and proves those failures stop at
  the barrier. Runtime tests likewise prove unknown future manifest, gate, and
  receipt schemas never reach deserialization.
- Runtime authorization uses an external exact-receipt SHA256 allowlist as its
  trust anchor; receipt, gate, candidate manifest, and decision fields are
  mutually hash-bound. This is implemented trust plumbing, not evidence that a
  real independent authority has approved a candidate.

## Remaining work

- Populate the confirmation contract with a real, independently controlled
  physical cohort and independently generated candidate/baseline predictions;
  the implemented producer cannot create absent flights or authority.
- Populate the per-class calibration producer with enough independent physical
  lineages to clear the final policy minimum (20/class); current code production
  does not create that absent evidence.
- Optionally replace the exact-receipt allowlist with a managed signing-key
  service if deployment requires signer identity and key rotation. Do not treat
  this optional hardening as a substitute for real independent approval.

## Acceptance criteria

- Validator metrics exactly match trainer/calibration metrics on the same frozen
  real development lineages.
- Low recomputed Macro-F1, insufficient lineages, high ECE, tampered inputs,
  edited metrics, altered gate policy, or foreign evidence all fail.
- Candidate-mode output always has `release_authorized=false`.
- Only an independently trusted receipt bound to exact candidate and gate hashes
  makes runtime load schema-v3 artifacts.
