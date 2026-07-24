# Trust-First Diagnostics Implementation

This document describes the implemented reliability layer, its evidence
boundaries, and the commands needed to reproduce it. The product is a
post-flight triage assistant. It is not an airworthiness or safe-to-fly
certificate.

## What is implemented

### Selective diagnosis contract

The public decision state is one of:

| State | Meaning |
|---|---|
| `confirmed` | The available telemetry supports the required capability and the candidate passes the current evidence and separation gates. |
| `uncertain` | A candidate exists, but confidence, capability quality, competing findings, or ML risk control prevents confirmation. |
| `insufficient_data` | Required telemetry is missing, unsupported, corrupt, or could not be extracted. |
| `no_fault_detected` | No supported detector fired while the available capability checks did not block the result. This does not mean safe to fly. |

Each decision includes machine-readable abstention reasons, the required
diagnostic capability, its status, and the selection-policy version.

### Fail-closed ML risk control

`models/risk_control.json` is linked to the saved model by:

- model version;
- training-dataset identifier;
- saved holdout flight count.

ML can contribute to `confirmed` only when all of the following are true:

1. the artifact matches the loaded model manifest;
2. the ECE gate passes;
3. the false-critical-rate gate passes;
4. calibration is independent of model fitting and threshold tuning;
5. the artifact explicitly enables confirmation.

The current saved model is intentionally `advisory_only`: its 22-flight
holdout ECE is `0.1268385705`, above the `0.08` target, and no independent
false-critical calibration set is recorded. ML hypotheses remain visible, but
they cannot inflate rule confidence or independently produce a confirmed
diagnosis.

This is risk gating, not a claim of conformal coverage. Conformal risk control
becomes appropriate only after a sufficiently sized, flight-group-isolated
calibration set exists.

### Auditable temporal evidence

`src/diagnosis/temporal_evidence.py` evaluates a deliberately small temporal
logic subset:

```text
cause -> F[min_delay,max_delay] effect
```

The result is `satisfied`, `violated`, or `not_evaluable`. Temporal evidence
can support or contradict an existing hypothesis, but it never creates a
failure label by itself.

The first rules cover physically motivated relations such as vibration before
EKF degradation, GPS degradation before EKF degradation, and power instability
before motor stress.

### Multichannel Matrix Profile candidate

`src/diagnosis/matrix_profile.py` provides a bounded NumPy implementation of a
z-normalized multivariate Matrix Profile. It searches for a discord window
across available vibration, GPS quality, motor spread, battery voltage, and
attitude-error channels.

Its output is explicitly label-free:

- candidate onset and duration;
- nearest matching window;
- discord score;
- contributing channels.

It is evidence for a reviewer, not a root-cause verdict.

### Reproducible SITL scenarios

`simulation/sitl_scenarios.yaml` contains versioned scenarios for baseline,
sensor, propulsion, power, wind, and cascade cases. The runner:

- validates every mutated parameter uses the `SIM_` namespace;
- verifies the target is SITL before mutation;
- requires an armed vehicle before injection;
- reads original values before changing anything;
- restores all changed parameters in `finally`;
- writes provenance JSON;
- never creates fake `.BIN` files;
- marks synthetic output as evaluation-only and not training-eligible.

Validate or inspect scenarios without starting SITL:

```bash
python training/sitl_data_factory.py --validate
python training/sitl_data_factory.py --list
python training/sitl_data_factory.py --scenario gps_loss
```

Execute against an already-running, armed SITL instance:

```bash
python training/sitl_data_factory.py \
  --scenario gps_loss \
  --execute \
  --connect tcp:127.0.0.1:5760 \
  --output-dir build/sitl-runs \
  --log-path /path/to/SITL-generated-flight.BIN
```

The optional log path must refer to a real log produced by ArduPilot SITL. The
runner hashes and references it; it does not manufacture it.

## User-facing verification

After an editable install:

```bash
pip install -e .
ardupilot-diagnosis analyze sample.bin \
  --format json \
  --output build/selective_sample_report.json
```

The repository sample currently returns `uncertain`, not `confirmed`, because
the vibration capability is degraded and the top evidence score is below the
selection threshold. The report also includes a label-free multichannel
discord candidate. This is a smoke test, not a benchmark result.

## Current limitations

- No real SITL process is bundled or started automatically. Runtime injection
  still needs to be verified against an installed ArduPilot SITL environment.
- The Matrix Profile implementation is intentionally bounded and quadratic in
  the reduced point count. It is not a streaming detector.
- Temporal rules cover only explicitly encoded causal relations. Missing an
  edge means `not_evaluable`, not proof that no relation exists.
- Rule evidence scores are not calibrated probabilities.
- The current ML model is advisory because its risk-control gates fail.

## Next implementation decisions

1. Run the manifest against official ArduPilot SITL and preserve the generated
   `.BIN`, run record, ArduPilot commit, parameters, seed, and vehicle model.
2. Add grouped risk-coverage evaluation and flight-level bootstrap confidence
   intervals for rule-only, ML-only, and hybrid modes.
3. Convert temporal relations into a versioned causal graph with required,
   supporting, contradicting, and confounding evidence.
4. Add metamorphic real-log tests for timestamp shifts, sampling reduction,
   message loss, post-impact noise, truncation, and non-finite values.
5. Add DVC-style dataset snapshots and signed release attestations after the
   current trust behavior is accepted.
6. Evaluate MOMENT or Chronos-style embeddings only for retrieval and
   out-of-distribution scoring. They must not replace physics rules or emit
   autonomous root causes.

Research references and the broader prioritized roadmap are maintained in
[`RESEARCH_BACKED_NEXT_STEPS_2026.md`](RESEARCH_BACKED_NEXT_STEPS_2026.md).
