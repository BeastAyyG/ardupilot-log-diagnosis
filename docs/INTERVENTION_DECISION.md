# Intervention Decision (Goal 4)

Status: **decided 2026-08-26** per the pre-registered decision rule in the goal
brief, applied to `docs/FEATURE_GAP_REPORT.md` (commit c6def55).

## Decision

**Verified SITL parameter randomization**, implemented as an opt-in planning
layer (`synthetic_data/randomization.py`, planner flag
`randomization_enabled`, CLI `synthetic_data pair --randomize`, launcher env
`PAIR_RANDOMIZE=on|off`, workflow input `randomize: off|on`).

## Rule application

The audit measured MMD² = 0.6491 (p = 0.0020, permutation CI95 [−0.0143,
0.0449]) with 81/111 features significant at BH q < 0.05 and gaps spread
across power_bus, general_telemetry, spectral_content, magnetometer, gnss,
vibration_isolation, and state_estimation. That is a **broad physical gap
across multiple systems**, which selects *verified SITL parameter
randomization* over constrained augmentation (localized gap) or model-level
adaptation (residual multivariate gap). CORAL/TCA/reweighting remains the
documented fallback if randomization fails to close the gap.

## Parameter verification (live pinned firmware)

Every catalog entry was verified present in the live captured inventory of
the pinned build (1351 parameters,
`data/intervention/randomization_param_verification.json`, produced by
`ops/intervention/verify_randomization_params.py --inventory
parameter_inventory.parm`): **15/15 present, 0 missing**. The same check runs
per-plan at planning time: names absent from a captured schema are skipped,
never defaulted.

| Parameter(s) | Range | System | Audit target |
|---|---|---|---|
| SIM_GYR1/2/3_RND | 0–0.03 rad/s | inertial_noise | imu_gyr_*_std (~20× real) |
| SIM_ACC1/2/3_RND | 0–1.2 m/s² | inertial_noise | spectral / attitude gaps |
| SIM_BARO_RND | 0.05–0.9 Pa | state_estimation | altitude variance |
| SIM_MAG_RND | 0–0.012 G | magnetometer | mag feature gap |
| SIM_GPS1_NOISE | 0–2 m | gnss | gnss gap |
| SIM_GPS1_NUMSATS | 7–15 | gnss | fix geometry |
| SIM_VIB_MOT_MAX | 0–4 m/s² | vibration_isolation | vibration gap |
| SIM_VIB_FREQ_X/Y/Z | 25–110 Hz | vibration_isolation | frame resonances |
| SIM_BATT_CAP_AH | 0.8–6 Ah | power_bus | bat_curr_max 0 A degeneracy |

All draws are pre-arm startup parameters written through the proven `.parm`
path, so they cannot trip the in-flight collection gate; both members of a
pair fly identical randomized values (counterfactual pairing preserved), and
disabled mode reproduces the legacy plan byte-for-byte except for two empty
bookkeeping keys.

## Scaling plan

Start with **50 paired runs per fault type** (motor_imbalance first), measure
gap closure with the Goal-3 audit tooling (MMD/Wasserstein vs adaptation
pool), and scale only if closure improves without degrading fault-manifestation
gates. Ablation conditions for Goal 5: baseline sealed corpus (exists),
randomized corpus (this layer), augmented corpus, SITL+adaptation.

## Non-claims

No accuracy improvement is claimed from SITL execution or randomization;
closure evidence must come from distribution metrics on sealed data before any
model claim.
