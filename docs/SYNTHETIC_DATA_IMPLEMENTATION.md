# Synthetic Data Implementation

The implementation now lives in the separate
[synthetic_data](../synthetic_data/README.md) laboratory.

Start with:

- [workflow and commands](../synthetic_data/README.md);
- [research and cross-domain rationale](../synthetic_data/RESEARCH.md);
- [proposed acceptance gates](../synthetic_data/configs/acceptance_gates.json).

The authoritative policy is:

1. Native ArduPilot SITL creates every DataFlash BIN.
2. The commit, binary, and live parameter inventory are immutable inputs.
   Active execution re-enters a fresh Linux user/network namespace containing
   only an enabled loopback interface; that live isolation proof is receipt-bound.
3. Parameter ACKs and DataFlash PARM changes must agree.
4. A scenario-specific telemetry effect must manifest before labeling.
5. Pre-onset, transition, and mixed full-log fault rows are excluded.
6. Simulation is training-only; real incidents alone calibrate and score.
   Hyperparameter folds and fitting weights use independent group/lineage units,
   and exact copied windows are canonicalized before preprocessing.
   Search breadth is limited to 4/16/64 candidates according to independent
   training-lineage support and the full design is artifact-bound.
7. Synthetic augmentation is retained only after a paired real-lockbox
   bootstrap clears utility, calibration, recall, and false-critical gates.
8. Code-readiness claims are bound to the exact dirty Git snapshot, including
   index state and non-ignored untracked files, by
   `synthetic_data.readiness_receipt`; this remains separate from model release
   authority and physical-flight evidence.

No accuracy gain has been demonstrated yet because no run has completed the new
receipt and manifestation gates. The implementation is ready for the first
small paired pilot.
