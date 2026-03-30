# CITA Compass Suppression Regression

Manual proof for the mentor concern about post-crash compass hallucination.

## Scenario

1. A propulsion failure begins first and forces the aircraft into loss of control.
2. After impact, the magnetometer field becomes noisy because the airframe is broken and resting near current-carrying hardware.
3. A naive min/max pass would incorrectly report `compass_interference`.

## Expected CITA Behavior

- `motor_spread_tanomaly` or `_thrust_loss_tanomaly` occurs before `mag_tanomaly`.
- The Hybrid Engine selects the earliest causal hypothesis.
- The final report includes hypothesis scaffolding showing the propulsion event first and the compass event as downstream noise.

## Current Regression Coverage

- Temporal arbitration implementation: `src/diagnosis/hybrid_engine.py`
- Public behavior documentation: `README.md` section `Crash-Immune Temporal Arbitration (CITA)`
- Automated regression: `tests/test_hybrid_engine.py::test_hybrid_engine_emits_hypothesis_scaffolding`

## Pass Condition

The selected root cause is propulsion-related, and the arbiter rationale states that it preceded the later navigation or compass symptom.
