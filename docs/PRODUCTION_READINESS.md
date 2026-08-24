# Production Readiness Plan

## Current decision

**Do not promote an ML artifact yet.** The application and rule engine are
operational, but no available ML artifact passes every release gate.

| Gate | Current result | Release decision |
|---|---:|---|
| Runtime feature schema | 111/111 finite features | Pass |
| Candidate model schema | 111/111 features, 9 trained labels | Pass with rules-only labels |
| Honest grouped candidate log Macro F1 (`v3_unambiguous`) | 0.500 (target >= 0.700) | Fail |
| Honest grouped holdout | 23 source incidents (target >= 50) | Fail |
| Honest candidate incident-level ECE | 0.153 (target <= 0.080) | Fail |
| Candidate per-class ECE | Multiple classes > 0.08 | Investigate |
| Full label coverage | 5 labels have no positive source logs | Fail |

Exploratory grouped retraining does not change that decision: the best fixed
holdout ExtraTrees run reached Macro F1 **0.596**, but incident ECE was **0.170**.
Across five grouped seeds it averaged F1 **0.584 ± 0.025** and ECE
**0.167 ± 0.006**; out-of-fold temperature scaling only reduced test ECE to
about **0.117**.

These historical model measurements are not evidence for the new synthetic-data
candidate path. The current code state is recorded separately by the
non-promoting machine receipt in
`synthetic_data/reports/readiness_receipt.json`. Regenerate it only after source
changes are final with `python -m synthetic_data.readiness_receipt build`, then
run the corresponding `verify` command. That receipt binds tracked, staged,
deleted, and non-ignored untracked source state plus verification outputs; it
does not authorize a model or demonstrate an accuracy gain.

The improved candidate `v4_improved` (2026-08-06) incorporated mutual information
feature selection (50 features), auto-label integration (+22 logs), synthetic data
boostrapping for missing classes (156 incident groups total), soft-voting ensemble
modeling, and post-hoc temperature scaling ($T = 1.4714$). It achieved a grouped
log Macro F1 of **0.691** (nearing the 0.700 gate), reduced incident ECE to **0.086**
(nearing the 0.080 gate), expanded trained label coverage to **14/14 classes**, and
eliminated all 3 FastAPI lifespan deprecation warnings. These experiments are recorded
in `training/candidates/v4_improved/experiment_report.md` for reproducibility.

The 2026-08-05 forum acquisition pass is preserved in
`data/raw_downloads/forum_all_filtered_2026_08_05/`. It found 31 manifest
rows, 16 downloaded payloads, and 13 usable real logs (11 direct `.BIN`, one
`.TLOG`, and one `.BIN` inside an archive); the rest were HTML previews,
malformed payloads, or unavailable. No new labels were merged: the usable
`.BIN` with expert discussion still needs an explicit reviewer taxonomy label.
| Real-log integration | 43/43 crash-free; 7/7 golden labels present | Pass |

An earlier evaluation report recorded 0.723 log Macro F1, but the live
artifact associated with that report has a stale 94-feature schema, no
versioned window contract, and no input provenance. It is supported only as a
**legacy compatibility model**, not a production-signed release. The earlier
`v2_111` score of 0.670 used filename-only grouping and column-order
primary-label fallback. `v3_grouped` also exposed two source-URL groups with
contradictory labels and is rejected by the ambiguity gate. The safe
`v3_unambiguous` rerun excludes those four files and is the authoritative
honest baseline (F1 0.500, incident ECE 0.153).

## What is now production-hardened

- The shared feature pipeline always returns finite numeric values.
- Power, PID, derived, POWR-only system, and IMU-only FFT features are wired
  into the 111-feature runtime schema.
- Training, runtime ML, and candidate artifacts share one time-window contract:
  windows plus the full log, max raw class probability aggregation.
- Model artifacts record ordered schemas, input file hashes, grouped-holdout
  metrics, threshold hash, and windowing metadata.
- `training.validate_artifact` fails closed before an artifact is promoted.
- The dashboard rejects malformed logs with a useful HTTP 422 response.
- Fleet HTTP routes fail closed unless `ARDUPILOT_FLEET_TOKEN` is configured;
  bearer headers are preferred and legacy query tokens remain supported.
- CORS is same-origin by default.  Cross-origin access requires an explicit
  `ARDUPILOT_CORS_ORIGINS` allowlist, and wildcard origins never receive
  credential support.

## Required data work

The current corpus has 114 usable source logs. It has no positive examples for
`brownout`, `crash_unknown`, `mechanical_failure`, `setup_error`, or
`thrust_loss`; those diagnoses must remain rule-only until labelled data exists.

1. Collect at least 10 independently sourced, expert-labelled logs for each
   missing root-cause class. Treat 5 source logs as the minimum to start an
   experiment, not a release-quality target.
2. Grow the untouched grouped holdout to at least 50 source logs, with at least
   two examples per release label and no SHA duplicate shared with training.
3. Record forum/maintainer provenance, SHA256, vehicle type, firmware, and the
   earliest causal evidence for every label. Do not label a final crash symptom
   as a cause when the log shows an earlier vibration, power, or control fault.
4. Capture high-rate IMU/VIBE, BAT/CURR, PID, ESC, GPS, EKF, and event data.
   Sparse logs may be accepted for limited rule checks, but should not train
   high-confidence ML classes.

## Candidate workflow

Build a new candidate in isolation; never overwrite `models/` while testing:

```powershell
python -m training.build_dataset --ground-truth <ground_truth.json> --dataset-dir <logs> --features-out training/candidates/<id>/features.csv --labels-out training/candidates/<id>/labels.csv --groups-out training/candidates/<id>/groups.csv --report-out training/candidates/<id>/dataset_build_report.json --window-sec 30 --overlap 0.5

python -m training.train_model --features-csv training/candidates/<id>/features.csv --labels-csv training/candidates/<id>/labels.csv --groups-csv training/candidates/<id>/groups.csv --model-dir models/candidates/<id> --dataset-report training/candidates/<id>/dataset_build_report.json --evaluation-report training/candidates/<id>/evaluation_report.md

python -m training.measure_ece --features-csv training/candidates/<id>/features.csv --labels-csv training/candidates/<id>/labels.csv --groups-csv training/candidates/<id>/groups.csv --model-dir models/candidates/<id> --report-path training/candidates/<id>/ece_report.json

python -m training.validate_artifact --model-dir models/candidates/<id> --features-csv training/candidates/<id>/features.csv --labels-csv training/candidates/<id>/labels.csv --groups-csv training/candidates/<id>/groups.csv --ece-report training/candidates/<id>/ece_report.json
```

Promote only if validation returns `"pass": true`, the candidate improves over
the active model on the same frozen holdout, and a reviewer signs off on the
error analysis. Launch a candidate for shadow testing by setting
`ARDUPILOT_DIAGNOSIS_MODEL_DIR=models/candidates/<id>` in a separate service;
do not replace the active model files during evaluation.

## Scope that remains explicitly review-only

Temporal smoothing is a deterministic persistence layer, not a trained HMM.
Webhook delivery, AMC parameter workflows, and parameter recommendations do
not autonomously modify aircraft. Video overlays are timing aids, not causal
proof. These boundaries must remain visible in releases.

## Runtime operations and deployment checks

The HTTP service exposes probes suitable for Docker/Kubernetes and a small
Prometheus-compatible metrics surface:

```text
GET /healthz       # process liveness; always cheap and side-effect free
GET /readyz        # dependency/model readiness; 200 or 503 with health.v1 JSON
GET /metrics       # process-local request counters and duration sums
```

`/readyz` reports `status: degraded` with HTTP 200 when the deterministic
rules/quality engine can serve requests but the configured ML artifact is a
legacy compatibility bundle or has not passed release gates. Set
`ARDUPILOT_REQUIRE_ML_MODEL=1` to fail readiness when the ML bundle is absent,
and set `ARDUPILOT_REQUIRE_RELEASE_MODEL=1` to require a versioned artifact
whose grouped Macro F1 is at least 0.70 with at least 50 held-out source
incidents.
The response includes artifact schema validity, feature/label counts,
evaluation metrics, and stale-manifest detection without deserializing model
weights on each probe.

The container runs as an unprivileged `app` user and has a Docker healthcheck.
Uploaded flight logs are streamed to temporary files and capped at 64 MiB;
JSON requests are capped at 8 MiB and flight comparison accepts at most 16
files. Request IDs are returned in `X-Request-ID` and security headers are
added to every HTTP response. Logs contain method/path/status/duration but no
uploaded payloads or query tokens. Framework errors (404, validation, auth,
and unexpected failures) retain FastAPI's `detail` field while also returning
the versioned `code` field from `src/error_codes.py`.

Before exposing a deployment, configure secrets outside source control:

```powershell
$env:ARDUPILOT_FLEET_TOKEN = "<random-long-secret>"
$env:MAVLINK_AUTH_TOKEN = "<random-long-secret>"
# Optional separate frontend:
$env:ARDUPILOT_CORS_ORIGINS = "https://dashboard.example"
# Strict model promotion gate (recommended for production):
$env:ARDUPILOT_REQUIRE_RELEASE_MODEL = "1"
```

Fleet and live-MAVLink HTTP/WebSocket controls fail closed when their tokens
are missing. CORS is same-origin by default; never combine a wildcard origin
with credentials. Use a reverse proxy/TLS terminator for internet-facing
deployments and scrape `/metrics` from a trusted network only.

`docker compose up` starts only the core engine. The temporal HMM and grounded
explanation service are explicitly review-only and can be enabled with
`docker compose --profile experimental up`; the unconfigured nginx gateway is
kept behind the `gateway` profile until a real reverse-proxy configuration is
provided.
