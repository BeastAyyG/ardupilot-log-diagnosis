# Goal 07 — Run the Real Accuracy Experiment

## Copy/paste prompt

Run the preregistered experiment that can determine whether verified synthetic
ArduPilot data improves diagnosis. This goal requires external ArduPilot builds,
SITL compute, expert-reviewed physical logs, and independent confirmation
authority. Do not execute real vehicle controls; SITL execution must remain
loopback-only. Do not claim success from development data.

## Experimental sequence

1. Inventory and deduplicate real physical-flight lineages. Record firmware,
   frame, vehicle, mission phase, environment, sensor/logging quality, label
   authority, and physical-flight verification.
2. Freeze declared classes, scenarios, extraction contract, split ledger,
   manifestation predicates, fidelity design, OOD domains, metrics, confidence
   methods, dose grid, stopping rule, and acceptance policy.
3. Run a tiny SITL predicate-development pilot only. Tune predicates here, then
   freeze and hash them; none of these runs enter verification evidence.
4. Generate a new paired sham/intervention verification corpus with exact owned
   receipts. The configured one-sided 95% zero-failure gates require at least
   59 fault manifestation units per scenario and 299 sham/parser units for a
   1% upper failure bound; recompute sample sizes if policy changes.
5. Measure conditional fidelity and OOD behavior. Block unsupported strata.
6. On real train/calibration/development partitions, compare real-only baseline
   against preregistered verified-synthetic dose arms using atomic pairs. Select
   one candidate once; do not revisit the development test.
7. Acquire a new, never-opened, blinded physical confirmation cohort sized by
   preregistered precision/power analysis for Macro-F1 and simultaneous
   per-class recall non-inferiority.
8. Evaluate once. Bind predictions and all reports to the sealed evidence bundle.
   Independent authority reviews and signs/allowlists the receipt.

## Required success evidence

- Absolute real-confirmation Macro-F1 lower confidence bound meets policy.
- Paired Macro-F1 improvement lower bound is positive and every declared class
  meets simultaneous recall non-inferiority.
- Calibration, healthy false-alarm, severity-aware false-critical, fidelity,
  OOD routing, privacy, reproducibility, and execution gates all pass.
- Independent repeat passes on exact immutable inputs.
- Candidate remains inactive until separately authorized promotion receipt is
  verified by runtime.

If any requirement is absent, report the result as exploratory or blocked—not
as a real-world accuracy improvement.
