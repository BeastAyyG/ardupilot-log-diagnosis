# Research Basis and Cross-Domain Design

## Research conclusion

The strongest practical approach is a credibility-managed digital twin:
ArduPilot's real autopilot code runs against pinned flight dynamics, controlled
interventions are verified through independent channels, simulator uncertainty
is measured against real training flights, and diagnostic utility is decided
only on untouched real incidents.

Raw SITL logs preserve the production parser, message rates, temporal
structure, control-loop feedback, estimator response, and cross-channel
relationships. Hand-authored feature templates preserve none of those and can
make generator fingerprints trivially separable.

## Primary flight-domain sources

### ArduPilot execution and evidence

- SITL workflow:
  https://ardupilot.org/dev/docs/using-sitl-for-ardupilot-testing.html
- AutoTest framework:
  https://ardupilot.org/dev/docs/the-ardupilot-autotest-framework.html
- SITL parameters in source:
  https://github.com/ArduPilot/ardupilot/blob/master/libraries/SITL/SITL.cpp
- DataFlash structures:
  https://github.com/ArduPilot/ardupilot/blob/master/libraries/AP_Logger/LogStructure.h
- DataFlash documentation:
  https://ardupilot.org/dev/docs/common-logs.html
- External JSON flight dynamics:
  https://github.com/ArduPilot/ardupilot/tree/master/libraries/SITL/examples/JSON
- Estimator Replay:
  https://ardupilot.org/dev/docs/testing-with-replay.html
- Simulation on Hardware:
  https://ardupilot.org/dev/docs/sim-on-hardware.html

SITL parameter names change across revisions, and generated online references
often represent current source rather than a stable release. The implementation
therefore uses a live inventory from the exact built binary.

Useful current fault families include engine failure/multiplier bitmasks,
battery voltage/resistance, instance-specific GPS degradation, vector magnetic
interference, motor vibration, IMU/barometer/airspeed errors, RC/link loss,
external shove/twist, wind, and timing stress. Not every family exists or works
identically in every release.

### UAV datasets

- ALFA records real UAV failures and known fault times:
  https://arxiv.org/abs/1907.06268
- RflyMAD combines SIL, HIL, and real multicopter data:
  https://arxiv.org/abs/2311.11340
- BASiC contains 70 engineering-defined SITL flights:
  https://www.sciencedirect.com/science/article/pii/S2352340924000428

These sources motivate transfer experiments and onset-aware labels. They do
not prove that augmentation improves this classifier. BASiC must be classified
as simulation rather than real evidence.

## Lessons imported from other domains

### 1. Digital-twin verification, validation, and uncertainty

NASA's digital-twin formulation combines simulation, onboard health,
maintenance history, and fleet data:
https://ntrs.nasa.gov/archive/nasa/casi.ntrs.nasa.gov/20120008178.pdf

NIST frames credibility as verification, validation, and uncertainty:
https://www.nist.gov/publications/credibility-consideration-digital-twins-manufacturing

Translation:

- verification proves the intended build and parameter action ran;
- validation measures whether relevant simulated behavior resembles reality;
- uncertainty preserves remaining gaps rather than hiding them.

Kennedy and O'Hagan distinguish uncertain simulator parameters from structural
simulator discrepancy:
https://rss.onlinelibrary.wiley.com/doi/abs/10.1111/1467-9868.00294

Tuning wind, mass, or sensor noise cannot erase simplifications in motor,
battery, propeller, and environment models.

### 2. Robotics sim-to-real transfer

Domain randomization varies simulator conditions:
https://arxiv.org/abs/1703.06907

SimOpt and BayesSim adapt simulator distributions from real observations:

- https://arxiv.org/abs/1810.05687
- https://www.roboticsproceedings.org/rss15/p29.pdf

Start with bounded engineering ranges, then fit joint distributions from real
training logs or SystemID. Never tune simulation using calibration or lockbox
flights.

Important relationships include voltage sag with current/resistance, magnetic
disturbance with motor current, vibration with motor speed, mass/geometry with
inertia and hover throttle, and wind with control demand. Independent Gaussian
jitter breaks these relationships.

### 3. Design of experiments

Full Cartesian sweeps waste runs. Latin hypercube, Sobol,
fractional-factorial, and covering-array designs cover more interactions with
fewer experiments.

Translation:

- vary one physical cause first;
- cover severity, onset phase, intermittency, recovery, frame, mission, wind,
  firmware, logging quality, and sensor redundancy;
- create matched nominal, sham, and intervention runs;
- adaptively sample detector and failsafe boundaries later.

Sampling frequency is experimental coverage, not incident prevalence.

### 4. Rare-event safety testing

Adaptive stress testing searches efficiently for failure trajectories:
https://arxiv.org/abs/1902.01909

Use stress search for challenge/training cases, never as a fleet prevalence
estimate without a valid proposal distribution and likelihood-ratio weights.

### 5. Interventional causal learning

Fault injection creates interventions:
https://ojs.aaai.org/index.php/AAAI/article/view/26868

Lag-aware observational discovery such as PCMCI is complementary:
https://pmc.ncbi.nlm.nih.gov/articles/PMC6881151/

Store intervention intent, ACK, observed onset, manifestations, and causal
chain separately. An ignored or masked intervention is a failed experiment,
not a positive label.

### 6. Synthetic time-series evaluation

- Train-synthetic/test-real evaluation:
  https://arxiv.org/abs/1706.02633
- Classifier two-sample tests:
  https://arxiv.org/abs/1610.06545
- Maximum Mean Discrepancy:
  https://jmlr.org/papers/v13/gretton12a.html
- Temporal predictive/discriminative evaluation:
  https://proceedings.neurips.cc/paper/2019/hash/c9efe5f26cd17ba6216bbe2a7d26d490-Abstract.html

No marginal metric certifies fidelity. Check central distributions, tails,
missingness, rates, autocorrelation, dwell times, spectra, coherence, lagged
cross-correlation, transfer functions, state transitions, source-classifier
AUC, and downstream real utility by vehicle and flight phase.

The implemented feature-level report is a first gate. Raw-channel PSD,
coherence, and phase-stratified validation should follow after logs exist.

### 7. Predictive maintenance and degradation

NASA prognostics and C-MAPSS emphasize multivariate histories from nominal
behavior through degradation:

- https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/
- https://ntrs.nasa.gov/citations/20205001125

Future synthetic work should connect flights by vehicle history: motor
efficiency loss, growing vibration, capacity fade, rising resistance,
intermittent sensors, and maintenance resets. Evaluate warning lead time and
false alarms per flight hour.

### 8. Calibration, conformal prediction, and OOD

- Calibration:
  https://proceedings.mlr.press/v70/guo17a.html
- ECE weaknesses:
  https://openaccess.thecvf.com/content_CVPRW_2019/papers/Uncertainty%20and%20Robustness_in_Deep_Visual_Learning/Nixon_Measuring_Calibration_in_Deep_Learning_CVPRW_2019_paper.pdf
- Conformal assumptions:
  https://arxiv.org/abs/2107.07511
- Weighted conformal under shift:
  https://proceedings.neurips.cc/paper_files/paper/2019/hash/8fb21ee7a2207526da55a679f0332de2-Abstract.html
- Energy-based OOD detection:
  https://proceedings.neurips.cc/paper/2020/hash/f5496252609c43eb8a3d147ab9b9c006-Abstract.html

Calibrate only on real incidents. Report Brier, NLL, adaptive/classwise ECE,
reliability intervals, risk-coverage, and held-out firmware/frame/log-quality
domains. OOD routes to abstention or rules/review, not a confident new class.

### 9. Privacy

NIST warns that ordinary synthetic data is not automatically private:
https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-226.pdf

Remove or relative-normalize absolute GPS, time, callsigns, vehicle IDs, and
unique parameter fingerprints before sharing real-conditioned artifacts. Make
no privacy claim without a documented differential-privacy mechanism.

## Fault ontology

One target represents one observable primary cause. Orthogonal metadata keeps
root family, fault mode, temporal profile, flight phase, requested/measured
severity, outcome, observability, intervention success, and lineage.

Estimator rejection, failsafe, loss of control, and crash are outcomes. They
must not erase the upstream cause.

## Proposed evidence gates

These are project targets, not universal constants:

| Area | Gate |
|---|---|
| Provenance | 100% commit, binary, inventory, seed, mission, parameters, ACKs, onset, log hash, and lineage |
| Compatibility | 100% requested parameters exist and read back |
| Execution | at least 99% parser success after pilot stabilization |
| Manifestation | at least 95% accepted fault runs show the preregistered effect |
| Sham quality | at most 1% sham false manifestation |
| Leakage | zero payload, source-group, descendant, or lockbox overlap |
| Utility | lower paired-bootstrap 95% Macro-F1 delta above zero |
| Recall safety | no supported class loses more than five points |
| Calibration | real incident ECE at most 0.08; Brier/NLL no worse |
| False criticals | at most 5% and no material increase |
| OOD | target AUROC at least 0.85 with review fallback |
| Reproducibility | event order and metrics reproduce within tolerances |

Ten real positive incidents can begin an experiment, but cannot yield a tight
recall confidence interval.

## Recommended phased experiment

1. Fly three pairs for healthy/fault scenarios on one pinned build.
2. Validate every run manually; adjust only manifestation predicates.
3. Generate at least 30 independent lineages per supported class across frames,
   phases, severities, winds, and two firmware families.
4. Build real and synthetic features under one 30-second contract.
5. Freeze the real ledger before viewing augmented results.
6. Measure fidelity only on real training data.
7. Run identical seeds and synthetic-dose curves.
8. Retain only doses clearing utility, calibration, recall, and safety gates.
9. Add HIL/bench evidence for brownout/reset and manufacturer physics.
10. Only an independently authorized workflow may promote an artifact.
