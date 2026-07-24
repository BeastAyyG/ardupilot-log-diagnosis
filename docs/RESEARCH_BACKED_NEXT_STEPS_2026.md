# Research-Backed Next Steps — Trustworthy Diagnosis Without More Scraped Logs

## Product objective

Make the system trustworthy by controlling when it is allowed to answer,
showing auditable evidence, and failing safely outside its knowledge limits.
Do not treat another large model as a substitute for verified ground truth.

The recommended product description is:

> An evidence-based ArduCopter log-triage assistant with physics rules,
> causal-chain hypotheses, ML-assisted ranking, explicit capability checks,
> and mandatory abstention when evidence is insufficient. It does not certify
> airworthiness.

## P0 — Selective diagnosis contract

### Required output states

| State | Required condition |
|---|---|
| `confirmed` | Reliable capability, physics rule, two independent signals, valid causal edge, no close competitor |
| `uncertain` | Competing causes, ML-only result, weak support, or unresolved causal tie |
| `insufficient_data` | Required messages/rates absent, corrupt/truncated log, unsupported vehicle or firmware |
| `no_fault_detected` | Required capabilities reliable and no supported rule fires |

Never emit `safe_to_fly`.

### Why this is the highest-impact change

Selective classification explicitly trades coverage for lower error: a system
answers fewer cases so the answered subset is safer. The current project
already has abstention logic, but it should be evaluated with risk-coverage
curves and capability gates rather than one global confidence threshold.

Implementation:

1. pass the quality report into `HybridEngine`;
2. map each diagnosis label to required capabilities;
3. suppress incompatible rule and ML conclusions;
4. replace empty-result `healthy` with `insufficient_data` or
   `no_fault_detected`, depending on capability coverage;
5. report selective risk at 25%, 50%, 75%, and 100% coverage;
6. prevent ML-only results from entering `confirmed`.

Research basis:

- Geifman and El-Yaniv, [SelectiveNet: A Deep Neural Network with an Integrated
  Reject Option](https://proceedings.mlr.press/v97/geifman19a.html), ICML 2019.
- Angelopoulos et al., [Conformal Risk
  Control](https://proceedings.iclr.cc/paper_files/paper/2024/hash/f3549ef9b5ff520a7e41ff3cc306ab2b-Abstract-Conference.html),
  ICLR 2024.

Conformal risk control is a research candidate, not an immediate production
guarantee: the present calibration set is small and flight logs are not
exchangeable in the simple i.i.d. sense. Start with empirical grouped
risk-coverage curves and clearly labelled confidence intervals.

## P0 — Evidence semantics and rule provenance

Rename rule `confidence` to `evidence_strength` at the public interface. A rule
score is not a probability.

Every rule should publish:

- required messages and minimum sample rate;
- firmware/vehicle applicability;
- units and multiplier source;
- threshold source and version;
- onset window;
- supporting and contradicting signals;
- known confounders;
- a raw-telemetry chart or extract.

ArduPilot logs are self-describing through FMT, FMTU, UNIT, and MULT records.
The parser should validate field names, units, and multipliers rather than
assuming one fixed schema.

Primary references:

- ArduPilot, [Onboard Message Log
  Messages](https://ardupilot.org/copter/docs/logmessages.html).
- ArduPilot, [Storage and EEPROM
  management](https://ardupilot.org/dev/docs/learning-ardupilot-storage-and-eeprom-management.html).

## P0 — Safe AMC boundary

Do not export universal replacement values for battery, PID, motor, EKF, or
failsafe parameters.

The safe output is:

1. relevant AMC configuration step;
2. current parameter value;
3. firmware-defined range and enum;
4. reason the step needs review;
5. a proposed diff only when it can be derived from vehicle-specific facts;
6. explicit user approval;
7. a validation-flight procedure;
8. before/after log comparison.

Until these conditions are implemented, AMC output must remain advisory JSON
and must never be applied automatically.

Integration target:

- [ArduPilot Methodic
  Configurator](https://github.com/ArduPilot/MethodicConfigurator).

## P1 — Causal graph instead of earliest-onset-only

Temporal precedence is necessary but not sufficient for root cause. Encode an
explicit, versioned causal graph:

```text
power sag -> controller reset
motor saturation -> attitude error
motor imbalance -> vibration
vibration -> EKF variance
compass interference -> yaw inconsistency
GPS degradation -> position innovation growth
```

Each edge must define required evidence, maximum plausible delay, confounders,
and contradictory observations. If two findings are time-ordered but no causal
edge is supported, report a chain of observations and abstain from selecting
one root cause.

Research basis:

- He et al., [Hierarchical Causal Graph-Based Fault Root Cause Diagnosis and
  Propagation Path Identification for Complex Industrial Process
  Monitoring](https://doi.org/10.1109/TIM.2023.3268464), IEEE Transactions on
  Instrumentation and Measurement, 2023.
- Zhang et al., [An Industrial Fault Diagnostic System Based on a Cubic
  Dynamic Uncertain Causality
  Graph](https://www.mdpi.com/1424-8220/22/11/4118), Sensors, 2022.

## P1 — Metamorphic validation using existing logs

Metamorphic testing creates cases with known invariants without requiring new
expert-labelled flights.

Build transformations for the existing golden logs:

| Transformation | Required invariant |
|---|---|
| Long disarmed gap inserted | Armed-duration rates and diagnosis unchanged |
| Duplicate messages inserted | Aggregate diagnosis unchanged |
| Non-required message removed | Supported diagnosis unchanged |
| Required message removed | State becomes `insufficient_data` |
| Log truncated before causal onset | Root cause is not asserted |
| Post-impact MAG noise injected | Pre-impact root cause remains unchanged |
| Timestamps shifted uniformly | Relative causal order unchanged |
| Sample rate reduced | Capability degrades before diagnosis confidence rises |
| Unknown FMT message inserted | Parser remains forward-compatible |
| NaN/Inf injected | Fail-closed normalization, no high-confidence result |

Trace each transformation to a concrete failure hypothesis and safety
requirement.

Research basis:

- Speth et al., [Traceable Metamorphic Test Cases for Robust Safety-Critical
  Systems](https://onlinelibrary.wiley.com/doi/10.1002/stvr.70020), Software
  Testing, Verification and Reliability, 2026.

## P1 — Extract more evidence from the existing dataset

No additional scraping is required for these measurements:

1. freeze the current 22-flight holdout and never tune against it again;
2. run nested, group-isolated cross-validation by `flight_id`;
3. publish bootstrap confidence intervals at the flight level;
4. publish per-label support and disable labels with inadequate support;
5. compare rule-only, ML-only, and hybrid risk at equal coverage;
6. use two-reviewer adjudication on existing logs;
7. keep disagreements and symptom-only forum labels as `unknown`;
8. deploy ML only for labels whose lower confidence bound improves over rules.

Adaptive conformal inference is relevant for future fleet drift, but should be
tested only after enough sequential validation flights exist:

- Gibbs and Candès, [Adaptive Conformal Inference Under Distribution
  Shift](https://proceedings.neurips.cc/paper/2021/hash/0d441de75945e5acbc865406fc9a2559-Abstract.html),
  NeurIPS 2021.

## P2 — Two-pass, self-describing parser

For large logs, replace per-message dictionaries with:

1. pass one: count message types and read FMT/FMTU/UNIT/MULT schemas;
2. exact-size allocation of typed column arrays;
3. pass two: populate arrays and record parse-quality errors;
4. expose slices per armed interval;
5. benchmark time and peak memory on 1 MB, 20 MB, and 75+ MB logs;
6. retain the current defensive corrupt/truncated-log behavior.

This is more likely to improve real user experience than replacing XGBoost.

## P2 — Retrieval before a larger classifier

Use only human-verified cases as a case library. Return:

- nearest verified flight;
- matched evidence features;
- important differences;
- original diagnosis provenance;
- no match when similarity is weak.

Retrieval is inspectable and gives maintainers concrete precedent. It should not
convert an unverified forum statement into ground truth.

## P3 — Time-series foundation models as an experiment only

MOMENT and newer zero-shot anomaly models may provide useful embeddings for
similarity or out-of-distribution detection without training on more ArduPilot
labels. They should not replace the physics engine or produce autonomous root
causes.

Run a bounded experiment:

1. use embeddings only for retrieval/OOD scoring;
2. compare against the current 94-feature cosine baseline;
3. require group-isolated evaluation;
4. measure false-critical rate and latency;
5. reject the approach if it cannot improve the lower confidence bound.

Reference:

- Goswami et al., [MOMENT: A Family of Open Time-series Foundation
  Models](https://openreview.net/pdf?id=FVvf69a5rx), ICML 2024.

## Trust case and release governance

Use the NIST AI RMF structure as a lightweight trust case:

- **Govern**: intended use, owners, change approval, incident handling;
- **Map**: supported vehicles, firmware, messages, hazards, affected users;
- **Measure**: per-label error, FCR, ECE, risk-coverage, parser robustness;
- **Manage**: abstention, rollback, artifact hashes, safe defaults.

NIST emphasizes valid/reliable behavior, safe failure beyond knowledge limits,
transparency, and lifecycle evaluation:

- NIST, [AI Risk Management
  Framework](https://www.nist.gov/itl/ai-risk-management-framework).

## Execution order

| Order | Deliverable | Exit evidence |
|---:|---|---|
| 1 | Capability-enforced selective diagnosis | Unsupported signals cannot produce confirmed diagnoses |
| 2 | `insufficient_data` / `no_fault_detected` states | No code path equates missing findings with safe flight |
| 3 | Remove probability semantics from rule scores | CLI/API schema and docs distinguish evidence from probability |
| 4 | Safe AMC advisory contract | No universal parameter values; approval and validation required |
| 5 | Metamorphic golden-log suite | Each safety hypothesis has at least one transformation test |
| 6 | Grouped risk-coverage evaluation | Rule/ML/hybrid compared at equal coverage with intervals |
| 7 | Versioned causal graph | Every selected root cause follows a supported physical edge |
| 8 | Two-pass parser benchmark | Peak memory and runtime published on large logs |
| 9 | Verified-case retrieval | Every returned case has human-verification provenance |
| 10 | Foundation-model embedding experiment | Kept only if it beats the transparent baseline |
