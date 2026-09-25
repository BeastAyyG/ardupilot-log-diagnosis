# Goal 05 — Build Sealed Acceptance Evidence

## Copy/paste prompt

Implement a programmatic acceptance-evidence builder. It must assemble every
domain report into one common candidate/cohort binding, verify each source file,
and produce evidence that `synthetic_data.gates` can recompute. Manual JSON
composition is not acceptable. The gate remains technical/non-promoting; release
requires independent authority outside the candidate directory.

## Inputs

- Exact candidate manifest, classifier, features, labels, groups, dataset report,
  split ledger, extraction contract, prediction ledger, immutable code snapshot,
  dependency lock, and confirmation-cohort manifest.
- Source reports for provenance, execution, utility, calibration, safety,
  fidelity, OOD, privacy, and reproducibility.
- Frozen acceptance policy whose SHA256 is supplied from an external trust
  location, not copied from candidate-controlled evidence.

## Builder behavior

- Verify every source-report candidate/cohort/taxonomy binding and file hash.
- Require the schema-valid confirmation report produced from the separately
  frozen physical prediction ledger; its utility block must exactly equal the
  utility domain report.
- Require exact declared-class and required-scenario key sets everywhere.
- Canonicalize metrics and compute the metrics-bundle and common evidence hashes;
  both hashes cover confirmation protocol/report content, excluding only the
  authority receipt itself to avoid recursive signing.
- Emit an unsigned draft first. An independent authority reviews it and returns
  a signed or externally allowlisted receipt bound to candidate, cohort, policy,
  evidence, and metrics-bundle hashes.
- Recompute the gate from evidence/policy; never trust a supplied `pass` field.
- Refuse unknown schemas, NaN/Infinity, booleans as numbers, invalid rates/counts,
  missing strata/classes/scenarios, or reports from different candidates.

## Acceptance criteria

- Add a CLI such as `python -m synthetic_data bundle-evidence ...`.
- A complete fixture passes technical gates only when its independent receipt is
  trusted by the externally pinned policy.
- Mutating any metric, source report, cohort, class, scenario, candidate artifact,
  policy, or authority receipt invalidates the bundle.
- Output remains `release_authorized=false`; activation is a separate authority
  action.
