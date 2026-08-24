# Verified Synthetic Flight-Data Laboratory

This folder is the authoritative synthetic-data subsystem for logdiagnosis.
It plans and verifies native ArduPilot SITL flights; it never fabricates
DataFlash bytes or hand-authored feature vectors.

Current result: the infrastructure is implemented and tested, but no accuracy
gain is claimed yet. Development selection requires receipt-verified SITL logs
and a paired ablation; a gain becomes defensible only after the one selected
candidate also clears the new blinded physical-confirmation cohort and external
authority review.

## Why this design

Synthetic data is useful for controlled causes, rare operating conditions, and
coverage. It is dangerous when a model learns the generator rather than flight
physics. This laboratory therefore separates five questions:

1. Was the exact simulator build pinned?
2. Did the requested intervention exist and receive a live readback?
3. Did DataFlash independently record the parameter change?
4. Did the expected telemetry effect actually manifest?
5. Did those logs improve an untouched real incident set?

A run is trainable only when questions 1–4 pass. Synthetic augmentation is
retained only when question 5 passes with uncertainty bounds.

## Folder map

~~~text
synthetic_data/
  catalog.py       version-aware fault ontology and non-claims
  schema.py        commit, binary, and parameter-inventory binding
  planner.py       deterministic paired control/intervention plans
  runner.py        loopback-only pymavlink executor and ACK receipts
  collector.py     DataFlash identity, onset, and causal-effect gates
  splits.py        immutable real train/calibration/lockbox ledger
  fidelity.py      sim-real feature-gap diagnostics
  temporal_ledger.py dataset-bound extraction from raw DataFlash streams
  temporal_fidelity.py raw cadence/ACF/PSD/coherence/lag evidence
  ablation.py      real-only dose ablation with bootstrap intervals
  ablation_ledger.py deterministic per-lineage prediction evidence
  ood.py           frozen-threshold OOD metrics and runtime-route evidence
  confirmation.py  blinded physical-cohort identity and utility evidence
  cli.py           command-line workflow
  configs/         proposed measurable gates
  schemas/         portable data contracts
  RESEARCH.md      evidence base and cross-domain translation
~~~

Generated logs belong outside source control or under the ignored outputs
directory. Track only reviewed, share-safe manifests, hashes, and reports.

## Safety boundary

The executor:

- connects only to an explicit loopback IP;
- requires the exact local SITL binary SHA256;
- compares the complete live parameter-name inventory with the pinned schema;
- requires SITL-only parameters and the planned frame;
- refuses experimental scenarios through the default execution path;
- requires an explicit confirm-sitl option;
- never launches shell commands or connects directly to a flight controller.

Loopback alone is not proof of simulation, so the binary, live inventory, and
later DataFlash firmware hash are independent checks.

## End-to-end workflow

### 1. Build and pin ArduPilot SITL

Follow the official documentation:

- https://ardupilot.org/dev/docs/setting-up-sitl-on-linux.html
- https://ardupilot.org/dev/docs/using-sitl-for-ardupilot-testing.html
- https://ardupilot.org/dev/docs/the-ardupilot-autotest-framework.html

Inside the ArduPilot checkout:

~~~bash
git checkout <release-tag-or-commit>
git submodule update --init --recursive
git rev-parse HEAD
./waf configure --board sitl
./waf copter
~~~

Record the full 40-character commit. Never use master, main, latest, or a
floating container tag.

### 2. Capture the exact live parameter inventory

This is a one-time offline pinning step for building the parameter schema only;
MAVProxy must never be part of any run path:

~~~text
param fetch
param save parameters.parm
~~~

Bind the inventory to the commit and binary:

~~~powershell
python -m synthetic_data schema --inventory C:\experiments\parameters.parm --ardupilot-commit <40-character-commit> --binary C:\ardupilot\build\sitl\bin\arducopter --output C:\experiments\parameter_schema.json
~~~

Malformed names, conflicting duplicates, non-finite values, short revisions,
and invalid digests are rejected.

### 3. Plan matched controls and interventions

~~~powershell
python -m synthetic_data plan --parameter-schema C:\experiments\parameter_schema.json --runs-per-scenario 5 --seed 20260823 --scenario thrust_loss --scenario gps_quality_poor --output-dir C:\experiments\sitl_v1
~~~

Paired planning is the default. Every intervention receives a sham control with
the same frame, wind, duration, and lineage root. Run seeds are independent of
catalogue order, so adding a scenario cannot silently change prior runs.

Planning creates no BIN file. Pending labels remain non-trainable. Planning
into a non-empty unowned directory or overwriting a different experiment is
refused.

### 4. Launch one isolated SITL instance per run

The laboratory owns the simulator process directly. Do not use
`sim_vehicle.py`, MAVProxy, tmux, or any manual UDP relay: receipts produced by
a manually launched simulator cannot attest an owned, closed process tree and
collection will reject them.

One command stages, launches, flies, lands, fences, hashes, and publishes:

~~~bash
python -m synthetic_data execute --output-dir /srv/logdiagnosis-experiments/sitl_v1 --run-id <run-id> --endpoint tcpin:127.0.0.1:14550 --binary /opt/ardupilot/build/sitl/bin/arducopter --ardupilot-root /opt/ardupilot --confirm-sitl
~~~

Active execution must run on Linux or WSL with util-linux `unshare` and
unprivileged user/network namespaces enabled. The CLI automatically re-execs
the complete controller and ArduPilot child in a fresh network namespace,
raises only `lo`, and refuses execution if any external interface is visible.
The parent/child namespace IDs, loopback state, exact interface list, and
`unshare` binary hash are bound into receipt v4. Windows may prepare plans and
collect artifacts, but it cannot directly execute this release-grade path.

- `--endpoint` must be the exact loopback listener `tcpin:127.0.0.1:14550`;
  non-loopback endpoints are refused.
- `--confirm-sitl` attests that the endpoint is an isolated software simulator.
- The pinned ArduPilot source tree (`--ardupilot-root`) must be clean; its HEAD,
  tracked-tree state, and submodule state are hashed into the receipt.
- The generated direct-ArduCopter command pins `--speedup 1`, a fixed home,
  `--start-time`, sysid/component 1, and `--rc-in-port 0` so no native RC UDP
  listener is bound on `0.0.0.0`.

Excess speedup creates heartbeat, timing, and logging artifacts unrelated to the
intended fault, so speedup stays at 1.

The runner waits for ready state, arms, takes off, schedules the intervention
in simulator boot time, requires every PARAM_VALUE readback, keeps the logger
alive past disarm, terminates only the owned process group after the log is
stable, stages/fsyncs/hashes the BIN, publishes it atomically, writes an
execution receipt, and quarantines everything if publication fails.

### 5. Collect only causally verified logs

~~~powershell
python -m synthetic_data collect --output-dir C:\experiments\sitl_v1
~~~

Collection checks manifest/schema hashes, path containment, payload uniqueness,
BIN integrity, duration, vehicle, required messages, firmware identity, flight
state, parameter ACKs, DataFlash PARM changes near receipt boot times, adequate
pre/post telemetry, and a preregistered scenario effect.

An acknowledged intervention with no observable effect is quarantined, not
labeled positive. Experimental RC behavior requires explicit collection opt-in
and remains blocked from the default runner.

### 6. Build features without temporal label noise

Use exactly the same window settings for real and SITL data:

~~~powershell
python -m training.build_dataset --ground-truth C:\experiments\sitl_v1\ground_truth.json --dataset-dir C:\experiments\sitl_v1\logs --features-out C:\datasets\sitl_v1\features.csv --labels-out C:\datasets\sitl_v1\labels.csv --groups-out C:\datasets\sitl_v1\groups.csv --report-out C:\datasets\sitl_v1\dataset_build_report.json --window-sec 30 --overlap 0.5
~~~

For a fault log, pre-onset windows and the onset guard band are excluded. Only
post-onset windows receive the fault label, and the mixed full-log row is
excluded. Matched sham flights supply healthy context.

### 7. Merge only identical extraction contracts

~~~powershell
python -m training.merge_datasets --input C:\datasets\real_v1 --input C:\datasets\sitl_v1 --output C:\datasets\mixed_v1
~~~

Merging rejects missing provenance, unknown source types, unverified synthetic
rows, bad hashes, duplicates, and differences in feature/label schema,
extractor source, window size, overlap, transition guard, or full-log policy.

The BASiC dataset is simulation, not real holdout evidence. Its paper describes
70 engineering-defined SITL flights. It may be a research simulation source
only after explicit provenance; it cannot satisfy real-support gates.

### 8. Freeze real partitions

~~~powershell
python -m synthetic_data freeze-split --labels-csv C:\datasets\mixed_v1\labels.csv --groups-csv C:\datasets\mixed_v1\groups.csv --output C:\datasets\mixed_v1\real_split.json
~~~

Only explicit real lineages enter real_train, real_calibration, or
real_lockbox. Synthetic descendants enter none of them. Assignments are stable
under row reordering and bound to exact label/group files.

Terminology: `real_lockbox` is a **development test** set. Dose and model
selection consume it, so a passing ablation is still not release evidence; a
new, never-opened, blinded physical confirmation cohort is required afterwards.

### 9. Measure fidelity and utility separately

Preregister the strata denominator first, freeze it, and pass it explicitly so
the generator cannot omit difficult strata and still report full coverage:

~~~json
{
  "schema": "logdiagnosis.fidelity-design-manifest/v1",
  "minimum_units_per_domain_per_stratum": 3,
  "required_strata": [
    {"primary_label": "thrust_loss", "flight_phase": "hover",
     "vehicle_frame": "quad", "firmware_commit": "<40-char-commit>",
     "simulation_family": "thrust_loss"}
  ]
}
~~~

~~~powershell
python -m synthetic_data temporal-ledger --design C:\reports\temporal_design.json --logs-root C:\datasets\raw_logs --features-csv C:\datasets\mixed_v1\features.csv --labels-csv C:\datasets\mixed_v1\labels.csv --groups-csv C:\datasets\mixed_v1\groups.csv --split-ledger C:\datasets\mixed_v1\real_split.json --output C:\reports\temporal_ledger.json
python -m synthetic_data temporal-fidelity --ledger C:\reports\temporal_ledger.json --design C:\reports\temporal_design.json --features-csv C:\datasets\mixed_v1\features.csv --labels-csv C:\datasets\mixed_v1\labels.csv --groups-csv C:\datasets\mixed_v1\groups.csv --split-ledger C:\datasets\mixed_v1\real_split.json --output C:\reports\temporal_fidelity.json
python -m synthetic_data fidelity --features-csv C:\datasets\mixed_v1\features.csv --labels-csv C:\datasets\mixed_v1\labels.csv --groups-csv C:\datasets\mixed_v1\groups.csv --split-ledger C:\datasets\mixed_v1\real_split.json --design-manifest C:\reports\fidelity_design.json --temporal-ledger C:\reports\temporal_ledger.json --temporal-design C:\reports\temporal_design.json --output C:\reports\fidelity.json
python -m synthetic_data ablation --features-csv C:\datasets\mixed_v1\features.csv --labels-csv C:\datasets\mixed_v1\labels.csv --groups-csv C:\datasets\mixed_v1\groups.csv --split-ledger C:\datasets\mixed_v1\real_split.json --prediction-ledger C:\reports\ablation_predictions.json --output C:\reports\ablation.json
~~~

Start from
`synthetic_data/configs/temporal_fidelity_design.example.json`, replace both
all-zero hashes and the firmware placeholder with exact frozen values, review
the message/field/unit mappings, then freeze the file before extracting the
ledger. The extractor accepts only real-training lineages and accepted synthetic
lineages in the preregistered strata. It contains paths under `--logs-root`,
verifies raw payload hashes, rejects incomplete parses, applies frozen channel
selectors/scales, and records exact dataset/design bindings.

Fidelity compares verified simulation only with real training incidents. It
never inspects the development test. With a design manifest, the report carries
`design_required_strata`, `evaluated_required_strata`,
`missing_required_strata`, and the manifest SHA256; any missing or
under-supported stratum blocks the report.

Feature-level fidelity tests run within comparable label/phase/frame/firmware
strata on independent lineage units. They include linear and nonlinear C2ST,
a familywise permutation p-value, RBF MMD with a permutation p-value, balanced
real-real envelopes, and a simultaneous worst-stratum lineage-bootstrap bound.
Matched control/intervention arms are never counted as two independent global
lineages. Raw temporal fidelity is recomputed from the bound ledger because a
feature CSV cannot establish rate/jitter/dropout, ACF, PSD, coherence,
cross-channel lag, transition timing, or missingness behavior. The temporal
producer compares these metrics within preregistered strata using independent
lineages and a simultaneous real-real reference envelope. The acceptance gate
requires the embedded report, exact candidate/dataset/design hashes, minimum
support, lineage resampling, and derived pass state; a manually entered boolean
cannot pass.

The ablation uses identical partitions and model seeds for real-only and
synthetic doses of 0.1x, 0.25x, 0.5x, 1x, and 2x. Calibration uses real
calibration incidents; scoring uses real lockbox incidents; the Macro-F1
difference receives a paired incident bootstrap interval. The deterministic
prediction ledger records one row per real lineage and arm, exact targets,
class-ordered probabilities, seeds, split/data hashes, and a report-bound file
hash. It remains development-only and cannot substitute for blinded
confirmation predictions.

Production hyperparameter selection is also invariant to exact window copies.
Cross-validation is allocated from one representative per frozen group/class
combination rather than row counts. Within every fit fold, exact
feature/target/evaluation-unit duplicates are removed before feature selection,
scaling, or model fitting; source-group/class weights are then recomputed from
those canonical rows and normalized to the number of independent lineages.
The three method identifiers are stored in both the manifest and serialized
classifier and are checked before and after deserialization.
Search breadth is also preregistered from independent training support: four
XGBoost candidates below 16 lineages, 16 candidates from 16–63 lineages, and
the full 64-candidate grid only at 64 or more. The exact grid, tier, support,
selection unit, metric, candidate count, and design hash are bound into both
artifacts. This limits multiple-comparison selection pressure on sparse data
while preserving the full search when evidence is large enough.

The report is non-promoting. Retention requires:

- lower 95% paired-bootstrap Macro-F1 improvement above zero;
- real incident ECE at most 0.08;
- healthy false-critical increase at most one percentage point;
- no supported class losing more than five recall points.

### 9a. Produce OOD evidence

Freeze OOD domains, minimum lineage support, the real-only calibration score
quantile, and the exact runtime OOD threshold hash before evaluating any OOD
records. The required domains are held-out firmware, held-out frame, real sensor
corruption, and unknown fault family. Then run:

~~~powershell
python -m synthetic_data ood --prediction-ledger C:\reports\ood_predictions.json --design-manifest C:\reports\ood_design.json --output C:\reports\ood.json
~~~

The producer recomputes lineage-level AUROC, detection at the frozen 5% ID-FPR
threshold, stratified bootstrap intervals, ID false-positive rate, per-domain
support/detection, threshold reproduction, near-duplicate isolation, and the
end-to-end abstention/rules/review route for every detected evaluation record.
Missing domains, weak support, a changed threshold, duplicate lineages, or a
broken runtime route fail closed. A structurally valid report is not evidence
until it is populated by real ID/OOD lineages and an exercised runtime route.

### 9b. Recompute blinded physical-confirmation evidence

After selecting exactly one final candidate, freeze a new physical cohort using
`confirmation_cohort_manifest.schema.json`. The independent evaluator writes a
class-ordered `confirmation_prediction_ledger.schema.json` containing candidate
and frozen-baseline probabilities for every lineage. Neither file may contain a
development, calibration, or training lineage, artifact, or near-duplicate
cluster. Then run exactly once:

~~~powershell
python -m synthetic_data confirmation --prediction-ledger C:\sealed\confirmation_predictions.json --cohort-manifest C:\sealed\confirmation_cohort.json --candidate-manifest C:\candidate\manifest.json --baseline-manifest C:\baseline\manifest.json --development-groups C:\datasets\development\groups.csv --development-split-ledger C:\datasets\development\real_split.json --bootstrap-draws 10000 --seed 20260823 --output C:\sealed\confirmation_report.json
~~~

This recomputes candidate and baseline Macro-F1, an absolute candidate lower
bound, the paired Macro-F1 delta interval, simultaneous per-class recall-delta
lower bounds, and exact per-class physical-lineage support. It verifies all file
bindings and rejects development/confirmation overlap at lineage, raw-artifact,
or near-duplicate-cluster level. The result is deterministic and non-promoting;
it becomes independently sealed only when the external authority binds it in
an allowlisted receipt.

### 10. Assemble sealed acceptance evidence

Assemble every domain report into one common-candidate bundle; the builder
verifies bindings, refuses NaN/Infinity, cross-candidate reports, and class or
scenario key drift, then computes the canonical metrics-bundle and evidence
bindings. The output is an unsigned draft:

~~~powershell
python -m synthetic_data bundle-evidence --candidate-json C:\reports\candidate.json --domain-report provenance=C:\reports\provenance.json --domain-report execution=C:\reports\execution.json --domain-report utility=C:\reports\utility.json --domain-report calibration=C:\reports\calibration.json --domain-report safety=C:\reports\safety.json --domain-report fidelity=C:\reports\fidelity.json --domain-report ood=C:\reports\ood.json --domain-report privacy=C:\reports\privacy.json --domain-report reproducibility=C:\reports\reproducibility.json --confirmation-cohort-sha256 <64-char-cohort-manifest-hash> --confirmation-report C:\sealed\confirmation_report.json --output C:\reports\evidence_bundle.json
~~~

The utility domain must equal the utility block recomputed by the confirmation
producer. Hand-entered confirmation metrics or booleans cannot pass. The common
metrics hash covers the embedded confirmation report as well as all nine domain
reports, so an authority receipt cannot be replayed after either changes.

Recompute the technical gate from the bundle, never trusting any supplied
`pass` field:

~~~powershell
python -m synthetic_data gate --evidence C:\reports\evidence_bundle.json --policy C:\trust\acceptance_gates.json --output C:\reports\gate_report.json
~~~

Activation is a separate authority action: a promotion receipt is valid only
when its exact file SHA256 is pinned by the external trust anchor (for example
the `LOGDIAGNOSIS_TRUSTED_PROMOTION_RECEIPTS` environment variable maintained
outside the candidate directory). Without a pin, schema-v3 candidates stay
inert and `release_authorized` remains false.

### 11. Bind code verification to the exact dirty source state

After code and documentation changes are final, generate and immediately verify
the non-promoting readiness receipt:

~~~powershell
D:/logdiagnosis/.venv/Scripts/python.exe -m synthetic_data.readiness_receipt build --root D:/logdiagnosis-codex --output D:/logdiagnosis-codex/synthetic_data/reports/readiness_receipt.json
D:/logdiagnosis/.venv/Scripts/python.exe -m synthetic_data.readiness_receipt verify --root D:/logdiagnosis-codex --output D:/logdiagnosis-codex/synthetic_data/reports/readiness_receipt.json
~~~

It binds HEAD, branch, index state, working bytes, deletions, non-ignored
untracked files, submodules, verification output hashes, JSON parsing, runtime
versions, and limitations. The output path is the sole explicit exclusion. Any
other source change invalidates verification. This receipt proves only which
code state passed the recorded checks; it is not a model-promotion receipt and
does not demonstrate accuracy.

## Labels and honest claims

| Synthetic label | SITL can establish | SITL cannot establish |
|---|---|---|
| healthy | nominal control trajectory | absence of every possible real fault |
| vibration_high | increased IMU/VIBE response | bearing, propeller, or frame defect |
| motor_imbalance | partial output-effectiveness loss | the failed physical component |
| thrust_loss | complete output-effectiveness loss | propeller versus motor/ESC/wire |
| gps_quality_poor | fix/satellite degradation | the RF or antenna cause |
| compass_interference | current-correlated magnetic bias | a wiring or field source |
| power_instability | voltage/sag degradation | controller reset or real brownout |
| rc_failsafe | simulated link-loss response | range or receiver hardware cause |

Never synthesize crash_unknown: a controlled intervention is known. Do not
label engine loss mechanical_failure. Treat EKF failure as a manifestation
unless a separately verified software defect is the actual cause.

## What remains before an accuracy claim

No receipt-verified corpus has yet been flown with this laboratory. Therefore
there is no real-plus-SITL result and no demonstrated model improvement. The
next evidence-producing action is a small paired pilot, followed by collection
and the frozen ablation. Scale generation only after that pilot clears the
gates.
