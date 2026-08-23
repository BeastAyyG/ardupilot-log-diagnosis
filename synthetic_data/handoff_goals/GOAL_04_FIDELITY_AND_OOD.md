# Goal 04 — Implement Scientific Fidelity and OOD Evidence

## Current implementation status (2026-08-23)

- `synthetic_data/ood.py` now consumes a frozen OOD design and a candidate/runtime-
  threshold-bound prediction ledger. It derives lineage-level AUROC,
  detection-at-5%-ID-FPR, ID FPR, four required-domain detection rates and
  support, stratified bootstrap intervals, threshold reproduction, and runtime
  routing success.
- The OOD acceptance consumer now requires complete domains/support, valid
  ledger/design/threshold hashes, a reproduced frozen threshold, and
  `end_to_end_runtime` abstention/rules/review evidence.
- Failure tests cover a missing domain, cross-unit near-duplicate leakage, and a
  detected record that does not take the configured runtime route.
- The producer is implemented, but no real OOD ledger or exercised runtime route
  is present in this repository. Therefore OOD acceptance evidence and any
  accuracy gain remain unproven.
- Feature fidelity now derives conditional linear/nonlinear C2ST, a Bonferroni-
  corrected lineage permutation p-value, conditional RBF MMD, balanced
  real-real envelopes, and a simultaneous worst-stratum lineage-bootstrap
  bound. Global matched arms collapse to one lineage so paired controls are not
  pseudo-replicated.
- Raw-log temporal production is now implemented. A frozen design maps required
  channels to exact DataFlash messages/fields/selectors/units; the ledger builder
  selects only bound real-training and accepted-synthetic lineages, contains
  paths, verifies payload hashes, and rejects incomplete parses. The report
  derives rate/jitter/dropout, missingness, ACF, PSD-band fractions, coherence,
  cross-channel lag/correlation, and transition timing with simultaneous
  lineage-level real-real bounds.
- The acceptance consumer now rejects a standalone temporal pass boolean and
  requires the complete embedded report, candidate/dataset/design/ledger/method
  hashes, minimum support, duplicate audit, and lineage resampling. No real raw
  temporal ledger has been produced in this repository, so the evidence remains
  unavailable even though the producer is complete.

## Copy/paste prompt

Replace placeholder/first-stage fidelity and OOD claims with machine-derived,
candidate-bound evidence. Use a preregistered design manifest as the denominator;
do not let the generator omit difficult strata and still report full coverage.
All selection/tuning uses development data. Final numbers require a new blinded
real confirmation cohort.

## Required fidelity design

- Strata must cover declared scenario, label, frame, firmware family, mission
  phase, severity band, environment band, and source domain where applicable.
- Require minimum independent real and synthetic lineages in every required
  stratum; report missing strata explicitly.
- Compute balanced real-real reference envelopes within strata.
- Compute sim-real distances using linear and nonlinear source classifiers,
  source-classifier permutation distributions/p-values, MMD, and simultaneous
  worst-stratum uncertainty bounds.
- Add raw temporal evidence: rate/jitter/dropout distributions, ACF, PSD,
  coherence, cross-channel lag, transition timing, and missingness patterns.
- Avoid window pseudo-replication; bootstrap/permutation units are lineages or
  matched pair roots, stratified by declared class.

## Required OOD design

- Preregister OOD domains and minimum lineage support.
- Report AUROC and detection-at-5%-ID-FPR with uncertainty lower bounds.
- Exercise runtime end-to-end: every detected OOD incident must abstain or route
  to the configured rules/review path.
- Include near-duplicate and source-identity audits so OOD evidence cannot leak
  from train/calibration data.

## Acceptance criteria

- `synthetic_data/fidelity.py` consumes a frozen design manifest and reports
  design/evaluated/missing strata plus exact report hashes.
- Every acceptance-policy fidelity/OOD field is computed by code, not manually
  entered booleans.
- Tests demonstrate omission, low support, conditional failure, tampered report,
  and broken runtime routing all block acceptance.
- Reports clearly distinguish parser/control-loop realism from measured physical
  distributional fidelity.
