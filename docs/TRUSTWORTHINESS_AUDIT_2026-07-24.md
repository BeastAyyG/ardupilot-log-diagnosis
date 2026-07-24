# Trustworthiness Audit — 2026-07-24

## Scope

This audit records what was reproduced in the local repository, what the
current model artifacts actually support, and which claims remain outside the
available evidence. It is intentionally narrower than a product announcement.

## Reproduced software checks

| Check | Result |
|---|---|
| Full Python test suite | 219 passed |
| Ruff (`src`, `tests`, `training`) | Passed |
| Wheel build | Passed |
| Isolated wheel import | Passed |
| ML artifacts from isolated wheel | Loaded (`available`) |
| Dashboard HTML in wheel | Present |
| CLI demo outside repository | Passed |

The wheel audit found and fixed a packaging defect that had been hidden by
editable installs: the old wheel flattened the `src.*` package hierarchy and
omitted the model and dashboard assets. The corrected wheel preserves the
package hierarchy and installs model artifacts under
`share/ardupilot-log-diagnosis/models`.

## Real-log finding: wall time is not flight time

Reproduction log:

- File: `sample.bin`
- SHA256: `33C535F6F0EDB143BB85909901BE52BD73542206E3116AE9DDF22B1C42606CFB`
- Size: 987,473 bytes
- Messages parsed: 24,837
- Features extracted: 94

The previous parser used the first and last log timestamps as flight duration:

| Duration | Seconds |
|---|---:|
| Power-on/wall duration | 781.202818 |
| Sum of two armed intervals | 72.860463 |
| Overstatement factor | 10.7219x |

Because the quality engine divides message counts by duration, the old value
made valid telemetry appear roughly 10.7 times slower than it was during the
flights. The real sample was consequently reported as degraded or unsupported
for several analyses.

The parser now:

1. prefers `ARM.ArmState` records when present;
2. falls back to legacy `EV` IDs 10 (armed) and 11 (disarmed);
3. sums every armed interval in a multi-flight log;
4. closes a final interval at the last timestamp if the log ends while armed;
5. preserves `wall_duration_sec` separately;
6. uses armed `flight_duration_sec` for capability-rate calculations.

After the fix, the sample capability report is:

| Capability | Status |
|---|---|
| Vibration analysis | Degraded |
| Compass/GPS navigation | Reliable |
| Power/battery dynamics | Reliable |
| EKF state estimation | Reliable |
| Motor balance/mechanics | Reliable |
| PID rate control | Degraded |
| Event/failsafe tracking | Reliable |

Vibration and PID remain degraded because their measured rates sit at or below
the configured high-frequency-analysis thresholds. The corrected report no
longer misclassifies navigation, power, EKF, or motor analysis as low-rate.

Regression tests cover multi-flight EV intervals and the case where both ARM
and duplicate EV records are present.

## Current model evidence

| Property | Current value |
|---|---:|
| Unique flight groups in rebuilt feature table | 114 |
| ML-eligible flight groups | 110 |
| Training flight groups | 88 |
| Saved holdout flight groups | 22 |
| Calibrated macro F1 | 0.603 |
| Uncalibrated XGBoost macro F1 | 0.669 |
| Top-label ECE | 0.1268 |
| Production ECE target | <= 0.08 |

The ML bundle loads and predicts, but the calibration gate fails. Numeric ML
confidence is therefore advisory. The weakest holdout categories contain only
one flight, so label-level generalization cannot be claimed for those classes.

## Trust gaps that remain

1. Log-quality status is reported but does not yet suppress every incompatible
   diagnosis inside the hybrid engine.
2. `healthy` currently means no diagnosis was emitted; it must not be presented
   as an airworthiness or safe-to-fly conclusion.
3. Rule confidence is an evidence score, not a calibrated probability.
4. Earliest onset alone is temporal precedence, not proof of causation.
5. AMC export contains generic parameter values and is not equivalent to
   firmware-aware Methodic Configurator validation.
6. The list-of-dictionaries parser is less memory-efficient and less
   schema-generic than a two-pass FMT/FMTU-driven columnar parser.
7. The 22-flight holdout does not meet the documented production target of at
   least 50 independently reviewed holdout flights.

## Honest release classification

The current system is a working beta-quality, evidence-producing ArduCopter log
triage assistant. It is not an autonomous root-cause authority and must not
certify a vehicle as safe to fly.
