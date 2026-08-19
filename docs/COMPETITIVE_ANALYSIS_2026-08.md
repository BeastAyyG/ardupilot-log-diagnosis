# Automated ArduPilot Log Analysis: Competitive Analysis

**Reviewed:** 2026-08-03  
**Scope:** the tools in the [ArduPilot Discuss catalogue](https://discuss.ardupilot.org/t/list-of-automated-ardupilot-flight-log-analysis-software/143635), plus the official WebTools that establish the baseline.

This is a product comparison, not a claim that every advertised capability has been independently benchmarked.  `Verified` means it is described by the project's official repository/site or ArduPilot documentation; `Not publicly specified` means that source did not provide enough detail.

## Executive conclusion

This project is already differentiated by its deterministic+ML causal diagnosis, evidence-bearing output, local web/CLI/API modes, live MAVLink view, and multi-flight comparison.  Do **not** compete by making a general-purpose GCS or by letting an LLM decide a failure cause.  The community response to the catalogue specifically values engineering-grounded diagnostics.

The most valuable additions are:

1. **Configuration and hardware report** — inventory sensors/firmware/errors, export safe parameter subsets, and compare two parameter sets.
2. **Engineering tuning analyses** — reproducible FFT peak, notch/filter, PID step-response, and compass-fit recommendations, each with data-quality gates.
3. **Evidence provenance** — each threshold/rule should name its source and software version; every recommendation needs a confidence and a "do not auto-apply" safety rule.
4. **Portable reports** — versioned JSON plus self-contained HTML/PDF from the same canonical analysis result.
5. **Fleet persistence is later** — trends are already present; a database, retention policy, access control, and aircraft identity are prerequisites for fleet claims.

## Capability matrix

| Tool | What it demonstrably provides | Relative position to this project | Reusable lesson |
|---|---|---|---|
| **ArduPilot Hardware Report** | Firmware/board/sensor health, mission/Lua/parameter extraction, changed/minimal parameter exports, sensor-offset view. | Hardware inventory, detailed mission/Lua artifacts with hashes, changed/minimal/all parameter exports, validation, and semantic diff are implemented; full firmware-generated device metadata remains gated. | Keep firmware-specific metadata optional and preserve safe export/privacy modes. |
| **ArduPilot WebTools: MAGFit, Filter Review/Tool, PID Review** | Compass fitting; raw/batch IMU noise and filter what-if analysis; Bode plots; PID frequency-domain step-response review. | Auditable sphere-fit, FFT, filter/Bode, PID response, spectrogram, SysID, and review-only proposals are implemented; exact firmware WebTool parity is not claimed. | Keep focused analyzers independent and data-quality gated. |
| **ArduPilot AI Log Analyzer** | `.bin/.log` upload, chat, visualizations. Public page does not describe its decision logic. | Existing chat and dashboard overlap; our structured deterministic result is the stronger foundation. | Keep chat grounded exclusively in the canonical result. |
| **Omkar Sarkar GSoC concept** | Proposed structured engine; HMM used for temporal pattern/noise filtering, not primary root-cause classification. No published implementation was linked in the catalogue. | Our CITA causal ordering overlaps; temporal smoothing remains a valid incremental experiment. | Evaluate against noisy held-out logs before promotion. |
| **fossuav/aap** | ArduPilot coding playbooks; includes a log-analysis workflow. It is not an end-user analyzer. | Complementary, not a product competitor. | Adopt its source/navigation conventions when adding ArduPilot-specific checks. |
| **ALDA** | Rule-based causal diagnosis for nine fault classes, JSON, and static diagnostic plot. | Our engine has broader output/UI/ML/quality handling. | Keep a simple JSON/PNG-compatible fallback and explicit `unknown` path. |
| **BBAFlightHub** | ArduPilot+PX4 upload, motor/battery/GPS/EKF/FFT analysis, 2D/3D replay, chat, PDF/API, fleet registry and trends. | Local reports, PDF, generic PX4/TLog parsing, replay data, fleet persistence, and read-only chat/API are implemented; live/cloud GCS features remain intentionally out of scope. | Keep operational control separate from post-flight diagnosis. |
| **SmartTune CLI** | Offline multi-platform tuning; PID, FFT, filter, MagFit, hardware analyses; firmware parameter validation; structured output and read-only MCP tools. | PID/FFT/filter/MagFit/SysID/hardware analyzers, parameter catalog/search/validation, raw exports, plots, and report-only MCP tools are implemented for ArduPilot; an optional Orangebox-backed .bbl/.bfl adapter now supplies the shared telemetry contract for Betaflight logs. | Match its conservative validation and ±25%-style review boundary. |
| **Sathvik12004 analyzer** | Isolation Forest over normal flights; progressive multi-flight degradation comparison. | We have Isolation Forest and a trend analyzer. | Let users nominate known-good baseline flights; this makes anomaly scoring vehicle-specific. |
| **FUKUSHIMA / KURAGE GCS** | Browser GCS, live telemetry, planning, weather/airspace, fleet/video operations. | Adjacent operational platform, not a post-flight analyzer. | Avoid GCS scope creep; keep the live view diagnostic-only. |
| **PAPLAN** | Paid entry in the catalogue; no public technical capability detail was available during this review. | Not comparable from public evidence. | Revisit only if a public feature list becomes available. |
| **AYNA Flight Log Analyzer** | 44 automated checks across seven systems; explicit location/time/repetition context; log integrity, parameter, watchdog and arming checks; its wider product trends fleet maintenance. The current public analyzer is advertised as free despite the catalogue calling it paid. | A transparent local 44-card checklist now covers the same public categories with explicit required streams and pass/review/insufficient-data states; proprietary thresholds and scoring are not claimed. Timing/onset evidence, privacy-grid recurrence, configuration audits, maintenance records, baselines, and fleet trends are also implemented. | Keep each card evidence-bearing and independently regression-tested. |
| **aero-oli/ardupilot-binlog-analysis** | Agent skill with deterministic indexing/extraction, CSV/Parquet tables, Plotly graph packs, symptom-led investigations, custom derived plots, ArduCopter output mapping, and Methodic Configurator step reviews. | Parser/indexing, CSV/Parquet, derived series, self-contained interactive HTML graph packs, symptom diagnosis, artifact manifests, and Methodic step gates are implemented; exact skill prompt/reference parity is not claimed. | Keep the evidence contract and add fixtures for each supported step. |
| **ardupilot-mcp (Furkan Işıkay)** | Offline deterministic MCP server with natural-language explanation on top, configuration/pre-arm checks, physical power/thrust reasoning, and official documentation links. | Our read-only MCP facade and provenance contract cover the same integration shape. | Keep MCP transport report-only; expose explicit tool schemas and source-bearing findings, never raw-telemetry LLM diagnoses. |
| **FlightMD** | Multi-format PX4/ArduPilot/MAVLink engine; 0–100 health score, seven weighted modules, exact parameter fixes, PDF, GPX/KML, optional reverse geocoding, cross-flight diff/trends, maintenance records, and webhook alerts. | Generic ULog/TLog parsing, explainable score, PDF/GPX/KML, trends, maintenance, Methodic review, and local alert preview are implemented; reverse geocoding and actual webhook delivery remain explicit external integrations. | Keep exact parameter changes review-only and make external services opt-in with provenance. |

## Verified current-project capability baseline

| Capability | Current evidence |
|---|---|
| Deterministic causal diagnosis + ML support | `src/diagnosis/`, including CITA/hybrid engine and explicit decision policy |
| Parser and parameter extraction | `src/parser/bin_parser.py` |
| Diagnosis report/API/UI | CLI formatter, `src/web/app.py`, `src/web/index.html` |
| Live diagnostic telemetry | `src/web/live_stream.py` and live API routes |
| Multi-flight degradation comparison | `src/comparison/trend_analyzer.py`, CLI `compare`, and `/api/compare` |
| Parameter warnings / tuning advisor | `src/diagnosis/parameter_validation.py`, `src/tuning/advisor.py` |
| Agent-oriented structured export | `src/export/amc_exporter.py` and CLI `export` |

## Recommended implementation sequence

### P0 — make product claims exact

- Keep the input-capability registry authoritative across CLI, API, and UI. The web endpoint now accepts `.bin`, `.ulg/.ulog`, and `.tlog` only when their tested adapter dependency is available; vehicle-specific analyses remain capability-gated.
- Publish per-rule source links, applicable vehicle types, required log messages, thresholds, and missing-data behaviour. This is the most direct answer to community skepticism of "AI" diagnosis.
- Add golden real-log regression tests for each public diagnosis and each `unknown/insufficient-data` outcome.

### P1 — hardware and parameter report

Add a separate `HardwareReport` service/module that consumes the existing parsed log and emits:

- autopilot/firmware/build and detected vehicle;
- sensors and health/error/reset/log-quality summary;
- mission/Lua availability where logged;
- full, changed-only, and share-safe parameter exports; and
- a semantic parameter diff (`old`, `new`, unit/range when known, risk level).

This has a low dependency footprint because parameters and many system messages are already parsed. It is also a useful standalone report when there is no crash.

### P1 — evidence-first diagnostic checks

Move checks to declarative definitions with fields such as `id`, `source_url`, `required_messages`, `threshold`, `onset`, `severity`, `evidence`, `recommendation`, and `confidence_limit`. Start with the high-value missing checks surfaced by AYNA/Hardware Report: log integrity, watchdog resets, arming/pre-arm failures, configuration-vs-observed sensor mismatch, and repeat/location context.

### P2 — tuning toolchain

Implement in independent, testable analyzers:

1. FFT peak extraction with sampling-rate/data-quality validation.
2. Filter/notch recommendation with a Bode/phase-lag preview.
3. PID step-response metrics and conservative parameter deltas.
4. Magnetometer calibration fit and residuals.

Never write parameters to a vehicle. Produce a reviewable `.param` patch only after firmware/vehicle validation.

### P2 — reports and interoperability

- Make the Pydantic API response the canonical, versioned schema.
- Generate HTML and PDF from that exact result, embedding rule IDs and report version.
- Add an optional read-only MCP facade only after the core API schemas and error codes are stable.

### P3 — fleet work

Persist logs only with explicit operator ownership, encryption/access control, retention/deletion, aircraft/pilot identity, and migration-safe schema. Then extend the existing trend analyzer to per-aircraft baselines, maintenance intervals, and regression alerts. Do not build mission control, weather, airspace, or video operations into this diagnosis project.

## Detailed feature inventory

This is the actionable backlog behind the summary above.  Each item is intended to be a small, independently testable analyzer, rather than a large "AI" feature.  A **P0** item protects correctness or trust, **P1** is high-value post-flight work, **P2** is advanced engineering analysis, and **P3** needs persistent storage or external services.

### A. Ingestion, log quality, and flight segmentation

| Add | Minimum evidence/input | Result to return | Priority |
|---|---|---|---|
| File signature detection | first bytes, extension, parser probe | format, supported capabilities, clear unsupported-format error | P0 |
| Parser capability registry | format + vehicle + firmware family | a matrix of supported analyses, required message streams, and disabled reasons | P0 |
| Log integrity report | file size, parsed messages, `STAT`, log buffer/drop counters | `valid`, `partial`, `truncated`, or `insufficient_data`; message loss and confidence cap | P0 |
| Timestamp health | all `TimeUS` series | wraps, reversals, gaps, clock drift and time-normalisation decision | P0 |
| Data availability matrix | parsed message families and field coverage | which check can run, coverage %, sampling rate, and why any check was skipped | P0 |
| Flight-span detection | `STAT.isFlying`, ARM/DISARM, throttle, altitude, mode | takeoff/landing/armed segments; exclude bench/disarmed data by default | P1 |
| Phase segmentation | mode changes, altitude, speed, throttle, mission events | hover, climb, cruise, turns, descent, landing, and crash/impact intervals | P1 |
| Configuration-change segmentation | `PARM` changes, firmware/reboot markers | separate analysis windows before/after each change; prohibit cross-window tuning claims | P1 |
| Privacy scrubber | GPS, pilot/vehicle metadata, parameters | shareable report/log export with selectable coordinate rounding/removal and secrets allowlist | P1 |
| Raw-message explorer | message names/counts/field schemas | searchable, sampleable raw data view for experts and reproducible bug reports | P2 |

### B. Hardware, configuration, and firmware health

| Add | Minimum evidence/input | Result to return | Priority |
|---|---|---|---|
| Hardware inventory | boot text, `PARM`, sensor/device messages | board, firmware/build, frame/vehicle, sensor instances, CAN devices, GPS/airspeed/ESC availability | P1 |
| Sensor placement/config review | `INS_*`, `COMPASS_*`, orientation/position parameters | inconsistent orientation, missing use-mask, duplicate ID, offset sanity findings | P1 |
| CPU and memory health | `PM`, watchdog/internal-error/reset messages | loop-time/load/free-memory trends, reset timeline, overload verdict | P1 |
| Log throughput health | logging counters, buffer, dropped-message stats | drop rate, buffer headroom, affected message streams, logging configuration advice | P1 |
| Safe parameter export | parsed `PARM`, calibration and identity parameter taxonomy | full, changed-only, and redacted/minimal `.param` outputs | P1 |
| Semantic parameter diff | two parameter sets plus firmware parameter metadata | added/removed/changed values, unit/range, danger level, and linked docs | P1 |
| Parameter schema validator | firmware/version-specific parameter table | unknown/renamed/out-of-range values; never propose a parameter absent from that firmware | P0 |
| Parameter change audit | in-log `PARM` changes and mode/time context | who/when/what changed, flight phase, and potential effect | P2 |
| Mission/fence/rally/Lua extraction | DataFlash message types where available | downloadable artifacts and a manifest/hash for each | P2 |

### C. Deterministic safety and root-cause checks

| Add | Minimum evidence/input | Result to return | Priority |
|---|---|---|
| Pre-arm and arming audit | `MSG`, `ERR`, arming events, parameters | warnings before takeoff, recurrence, and whether flight proceeded despite them | P1 |
| Watchdog/internal-error classifier | watchdog/reset/internal-error messages | reset cause, time, recovery/termination behaviour, root-cause candidates | P1 |
| Failsafe taxonomy | `ERR`, `EV`, mode changes, RC/GCS/BAT/GPS streams | distinguish RC, GCS, battery, EKF, GPS, geofence and vibration failsafes; identify trigger vs response | P1 |
| Crash/end-of-log classifier | final attitude/altitude/velocity, errors, log integrity | expected landing, impact-like end, controller reset, or inconclusive end; confidence-capped for truncated logs | P1 |
| Event/message correlation | `ERR`, `EV`, `MSG`, mode changes and feature onset | a deduplicated timeline that connects a trigger to the autopilot response | P1 |
| Root-cause causal graph | existing candidate onset times plus dependency rules | directed cause/contributor/downstream-effect graph, not just a sorted label list | P2 |
| Counterfactual check | causal graph and anomaly windows | plain statement of what evidence would be expected if the competing diagnosis were true | P2 |
| Rule provenance | per-rule documentation URL, version, thresholds, vehicle applicability | source-bearing evidence card and exact rule version in JSON/HTML | P0 |
| Human-review queue | low confidence, missing data, rule conflicts | explicit questions and requested log/message data rather than a confident answer | P0 |

### D. Sensor, estimator, propulsion, and power analyses

| Add | Minimum evidence/input | Result to return | Priority |
|---|---|---|
| Multi-IMU consistency | multiple `IMU`/`IMU2`/`VIBE` streams | cross-sensor bias/noise disagreement and suspected sensor/mount issue | P1 |
| Accelerometer clipping attribution | `VIBE` clipping counters, throttle/RPM/ESC, FFT | onset and correlation to motor order/throttle; mechanical vs impact-noise confidence | P1 |
| Compass health and interference | `MAG`, current/throttle, EKF innovations, GPS/position | field norm/range, current correlation, motor-interference likelihood, location recurrence | P1 |
| Compass calibration fit | MAG + attitude + location/earth field + current/throttle | offsets, scale, iron matrix, motor compensation, residual and coverage score | P2 |
| GNSS quality and glitches | GPS fix/sats/HDOP/accuracy, EKF position innovation | no-fix time, fix degradation, glitch windows, multi-GPS disagreement and location evidence | P1 |
| Barometer and altitude consistency | BARO, GPS, EKF height, temperature | altitude disagreement, drift, temperature correlation and sensor plausibility | P1 |
| EKF lane/innovation analysis | `XKF*`/`NKF*`, flags/lane switches, sensor health | per-axis innovation timeline, source-switch events, primary precursor and downstream effects | P1 |
| Airspeed fit (Plane/QuadPlane) | `ARSP`, baro, EKF velocity/wind, POS, GPS, parameters | fitted `ARSPD_RATIO`, residual, identifiability/turn-coverage and conservative `.param` proposal | P2 |
| Motor/ESC imbalance | RCOU + ESC RPM/current/temp/voltage where logged | per-motor asymmetry, temperature/current/RPM correlation, likely prop/motor/ESC candidates | P1 |
| Motor order / direction plausibility | motor output, attitude response, actuator map/frame | testable mismatch suspicion; require a ground-test confirmation before any conclusion | P2 |
| Battery cell and sag model | voltage/current/capacity/temperature/parameters | cell-count plausibility, sag under load, consumed capacity, internal-resistance trend, reserve at landing | P1 |
| Battery failsafe margin | battery thresholds + voltage/current + mode/event timeline | threshold crossing, estimated margin, trigger/response and recalibration/maintenance suggestions | P1 |
| Payload / thrust margin | throttle, climb rate, motor output, battery, vehicle parameters | saturation duration and low-thrust condition; label unknown when mass/prop data are absent | P2 |

### E. Control, vibration, filters, and tuning

| Add | Minimum evidence/input | Result to return | Priority |
|---|---|---|
| Input-vs-output tracking | ATT/RATE targets + actuals, RC, actuator output | control error by axis, pilot-command vs autopilot-response separation | P1 |
| Actuator saturation / authority | RCOU/SERVO, throttle, attitude/rate error, mode | duration, axes and flight phase with insufficient-thrust vs command-limit hypotheses | P1 |
| PID component breakdown | PIDx messages; `RATE` fallback with limitation flag | P/I/D/FF terms, target/actual/error, parameter-change test sections | P2 |
| PID FFT and spectrogram | PIDx/RATE sampling rate and selected phase | spectrum, resolution, time-frequency resonance onset; only run with adequate sampling | P2 |
| PID step response | target/actual rate series and enough excitation | rise time, overshoot, settling, damping, confidence and no-recommendation result if unidentifiable | P2 |
| System identification | excitation-rich target/actual sequences | natural frequency, damping and model-fit score; experimental until validated on real held-out flights | P2 |
| FFT vibration peaks | raw/batch IMU (preferred) or recorded gyro, sample rate | per-axis PSD/RMS, peaks, harmonic families, confidence and required logging instructions | P1 |
| Vibration source attribution | FFT + throttle/RPM/ESC + phase segmentation | motor/prop/frame resonance likelihood, onset and verification steps | P2 |
| Filter-chain / Bode simulation | firmware-specific filter parameters | attenuation and phase-lag curve; overlay detected peaks and warn against aggressive filtering | P2 |
| Notch-filter proposal | verified peak plus valid parameter metadata | bounded centre/bandwidth/attenuation proposal and a review-only parameter patch | P2 |
| Thrust-expo analysis | thrust-test data or carefully qualified flight data | throttle-to-thrust linearity and `MOT_THST_EXPO` estimate; separate from crash diagnosis | P2 |

### F. Trajectory, operational context, and visual explanation

| Add | Minimum evidence/input | Result to return | Priority |
|---|---|---|
| Phase-aware replay | GPS/attitude/mode/time/events | replay with phase bands and causal markers; correct handling of missing GPS | P1 |
| Location recurrence | several logs with privacy-preserving coordinates | same-site issue clustering (magnetic/GNSS/airflow), never a causal claim from one flight | P2 |
| Mission compliance check | mission + GPS/mode/altitude/fence data | skipped waypoint, geofence/mode deviation, altitude/speed variance; vehicle-specific limits | P2 |
| Wind / weather context | EKF wind or explicit operator-provided/optional weather source | inferred wind confidence; external data provenance and offline fallback | P3 |
| Video synchronisation/overlay | video + log + manual/automatic sync points | exportable evidence video; isolate as an optional offline utility | P3 |

### G. Cross-flight baselines, maintenance, and fleet-level analysis

| Add | Minimum evidence/input | Result to return | Priority |
|---|---|---|
| Known-good baseline selection | user-labelled healthy flights for one aircraft/configuration | baseline provenance, feature distributions and eligibility checks | P1 |
| Configuration-aware trend analysis | ordered logs + airframe/config/firmware hashes | prevent comparing flights across changed hardware/firmware without a reset marker | P1 |
| Progressive degradation alerts | per-aircraft baseline + vibration/power/motor metrics | trend slope, change point, confidence, recommended inspection interval | P1 |
| Before/after maintenance comparison | two labelled groups plus configuration diff | what improved/regressed, statistical uncertainty and changed parameters | P1 |
| Flight-test acceptance template | vehicle profile + required checks/limits | pass/review/fail checklist and missing-data blockers for each test flight | P2 |
| Fleet quality dashboard | durable storage, identity, access control | aggregate reliability, firmware/hardware cohorts, failure distribution and drill-down | P3 |
| Regression analysis across firmware versions | fleet labels, config/vehicle cohorts, robust sample size | version comparison with confounder warnings; never infer firmware regression from unmatched populations | P3 |
| Maintenance records | durable aircraft identity and user-entered maintenance events | evidence-linked maintenance history and reminder suggestions | P3 |

### H. Reports, integrations, and safety boundaries

| Add | Minimum evidence/input | Result to return | Priority |
|---|---|---|
| Versioned analysis contract | canonical Pydantic result and schema version | compatibility policy, migration tests and report reproducibility | P0 |
| Self-contained HTML/PDF | canonical result + static charts | printable report with evidence, rule source/version, input hash and privacy notice | P1 |
| Expert hand-off bundle | redacted log/parameter export + JSON + plots + questions | a zip/manifest suitable for a forum expert without opaque AI prose | P1 |
| Read-only MCP service | hardened file paths, file-size limits and canonical result | `log_quality`, `analyze`, `hardware_report`, `compare`, `explain`; no shell or MAVLink writes | P2 |
| LLM grounding contract | canonical result, provenance and citations | LLM may explain or request data; it cannot create diagnoses/parameters absent from tool output | P0 |
| Local/offline mode | packaged parser/rules/charts and no required remote service | reproducible air-gapped analysis with clear optional-service boundaries | P1 |
| Error code taxonomy | parser, quality, analysis and report failures | stable machine-readable errors; no generic 500 for known user-input errors | P1 |
| Security limits | extension/magic validation, size/zip limits, temp-file lifecycle, safe report escaping | documented threat model and regression tests for malicious/corrupt inputs | P0 |

## Feature dependency map

```text
File parser + capability registry + quality report  [P0]
                 |
                 +--> hardware/config report ------> parameter validation/diff
                 |
                 +--> flight phases + event timeline --> deterministic checks --> causal graph
                 |
                 +--> sampled sensor series --------> FFT / PID / MagFit / AirspeedFit
                 |                                              |
                 |                                              +--> review-only parameter proposal
                 |
                 +--> canonical, versioned result --> HTML/PDF / expert bundle / read-only MCP
                                                        |
                                                        +--> per-aircraft baseline --> fleet trends
```

## What should not be added yet

- **Autonomous parameter writes, firmware flashing, or direct tuning changes.** A log analyzer should generate reviewable evidence and optionally a parameter patch, never mutate a flying vehicle.
- **A free-form LLM diagnosis of raw telemetry.** Keep rules/physics/validated models as the decision layer; use language models only for constrained explanation or tool orchestration.
- **A full mission-planning/GCS product.** Weather, airspace, live-video walls and dispatch duplicate mature operational systems and dilute this project's diagnostic credibility.
- **PX4/Betaflight format badges without complete adapters, fixtures, and vehicle-specific rules.** The optional Blackbox adapter is capability-level and generic; Betaflight-specific tuning rules remain explicitly gated until platform fixtures are added.

## Implementation status in this repository

The offline, read-only additions from the P0-P2 inventory are now wired into the
same parser/report contract used by the CLI, FastAPI, and dashboard:

- `hardware`, `param-diff`, `param-validate`, `report`, `capabilities`, and
  privacy-scrubbed `report --format bundle`, `acceptance`, `baseline`, and
  `maintenance` CLI commands;
- deterministic health scoring, GPX/KML track export, mission/waypoint and
  geofence review, hashed mission/configuration artifact export, Methodic
  Configurator step-gate review, ascent/recovery review for rocket/HAB-shaped
  logs, privacy-grid location recurrence, offline video timing sidecars
  (JSON/WebVTT/SRT), temporal persistence evidence, and a local fleet-alert
  preview (no webhook is sent by the analyzer), plus a transparent 44-card
  community checklist inspired by the public AYNA categories;
- `/api/hardware`, `/api/param-diff`, `/api/param-validate`, `/api/params`,
  `/api/mission/validate`, `/api/mission/compliance`, `/api/plot`,
  `/api/graph-pack`, `/api/artifacts`, `/api/derived-series`, and context
  endpoints for video overlay/location recurrence, plus `/api/capabilities`, `/api/acceptance`,
  `/api/baseline`, `/api/maintenance`, and a report-only `/api/tools/call`
  and `/mcp` facade;
- timestamp integrity, stream availability, flight/configuration segments,
  event timeline/temporal graph, safety/failsafe checks, and explicit source
  URLs on deterministic findings;
- battery sag/failsafe margin, compass sphere fit, GPS/dual-GPS quality,
  barometer drift, EKF variance, IMU consistency, ESC metrics, control tracking,
  actuator saturation, flight-span/phase context, raw-message explorer,
  configuration review, failsafe taxonomy, end-of-log classification, EKF lane
  review, propulsion/clipping attribution, FFT/spectrogram peaks, PID component
  and response summaries, system-identification experiment, notch proposal,
  mission/wind/location context, known-good baseline, maintenance comparison,
  acceptance checklist, local SQLite fleet reports/trends/maintenance events,
  and filter/Bode previews; and
- versioned JSON plus HTML/PDF/bundle exports with input hash, data-quality
  gates, CSV/Parquet/derived-series exports, deterministic PNG plots,
  self-contained interactive HTML graph packs with an embedded trajectory,
  WebTools-style hardware telemetry summaries (temperature, power rails, CPU,
  stack, composition, offsets, and per-stream clock health), hashed artifact
  manifests, a firmware-aware read-only parameter catalog (including
  caller-supplied firmware JSON), a stable error-code taxonomy, report-only
  read-only tool facades, and a clear read-only boundary.

The exact catalogue-to-implementation mapping is machine-readable via
`src/parser/catalogue.py`, `python -m src.cli.main catalogue`, and
`GET /api/catalogue`. It distinguishes local equivalents, offline subsets,
review-only experiments, and external/proprietary entries instead of hiding
those boundaries behind a generic "supported" badge.

The official WebTools Log Finder baseline is covered by the read-only
`log-finder` command: it detects supported formats, parses optional metadata,
groups logs by conservative vehicle/board/firmware identity, reports
parameter-change context, and can hash files without uploading them.

The registry reports PX4 ULog and MAVLink TLog as `available_generic`: they are
parsed into the common telemetry contract, while ArduPilot-specific parameter
semantics remain gated. ArduPilot text `.LOG` files use the DataFlash text
adapter. Persistent fleet storage, external weather/video, reverse geocoding,
webhook delivery, firmware-specific MAGFit/AirspeedFit parameter writes, and
vehicle control remain read-only or explicitly review-only and require
vehicle-specific validation.

The new catalogue entries are represented explicitly: aero-oli's Methodic and
custom-plot workflow maps to `methodic_review`, raw/derived/track exports,
artifact manifests, and self-contained HTML graph packs; the ardupilot-mcp and
SmartTune-style integrations map to explicit report-only tools and dynamic
parameter catalogs; FlightMD's score, GPX/KML, ascent/recovery, and alert ideas
map to deterministic local utilities; mission validation, location recurrence,
and video sidecars cover the offline operations subset without turning this
project into a GCS.

## Acceptance gates for every new analyzer

- Required source messages and sampling quality are reported; missing data yields `insufficient_data`, never a fabricated finding.
- A finding shows the raw evidence and first-onset time.
- A recommendation is read-only and capped/conservative; parameter changes require human review.
- Unit tests cover threshold boundaries and malformed/partial logs.
- A real-log regression fixture and expected structured output are checked into the test suite.
- Claims in README/UI cite the corresponding module and published benchmark, not a marketing comparison.

## Sources

- [Catalogue on ArduPilot Discuss](https://discuss.ardupilot.org/t/list-of-automated-ardupilot-flight-log-analysis-software/143635)
- [Official ArduPilot WebTools documentation](https://ardupilot.org/dev/docs/common-webtools.html)
- [Official WebTools development index](https://firmware.ardupilot.org/Tools/WebTools/Dev/)
- [ArduPilot Hardware Report](https://firmware.ardupilot.org/Tools/WebTools/HardwareReport/)
- [Hardware Report design notes](https://github.com/ArduPilot/WebTools/blob/master/HardwareReport/Readme.md)
- [MAGFit methodology](https://github.com/ArduPilot/WebTools/blob/master/MAGFit/Readme.md)
- [Filter Review methodology](https://github.com/ArduPilot/WebTools/blob/master/FilterReview/Readme.md)
- [PID Review methodology](https://github.com/ArduPilot/WebTools/blob/master/PIDReview/Readme.md)
- [AirspeedFit methodology](https://github.com/ArduPilot/WebTools/blob/master/AirspeedFit/Readme.md)
- [ALDA repository](https://github.com/Dijo-404/alda)
- [SmartTune CLI repository](https://github.com/raylanlin/smarttune-cli)
- [ArduPilot AI Playbooks repository](https://github.com/fossuav/aap)
- [Sathvik12004 analyzer repository](https://github.com/Sathvik12004/ardupilot-log-diagnosis)
- [BBAFlightHub](https://www.bbaflighthub.com/)
- [AYNA Flight Log Analyzer](https://www.ayna.com/log-analyzer/)
- [AYNA pilot tools overview](https://www.ayna.com/tools/)
- [KURAGE GCS repository](https://github.com/FUKUSHIMA-UAV/FUKUSHIMA)
- [aero-oli ArduPilot Bin Log Analysis skill](https://github.com/aero-oli/ardupilot-binlog-analysis)
- [ardupilot-mcp](https://github.com/furkanisikay/ardupilot-mcp)
- [FlightMD](https://github.com/Praddyx15/FlightMD)
