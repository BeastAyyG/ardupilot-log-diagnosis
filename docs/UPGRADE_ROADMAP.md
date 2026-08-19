# ArduPilot Log Diagnosis — v2.0 Platform Roadmap

**Author:** Agastya Pandey (BeastAyyG)
**Status:** Development roadmap — not a production-readiness statement
**Last Updated:** May 2026

---

## Vision

The current engine provides an offline rule + ML prototype, an Isolation Forest
anomaly detector, and a 3D replay. Its safe 111-feature candidate has not
passed the release gates (grouped log-level macro F1 0.500 on 23 holdout
incidents; incident-level ECE 0.153; minimum gates are F1 0.70, ECE 0.10,
and 50 independent holdout incidents). The earlier v3_grouped candidate is
invalid because two URL groups contain contradictory primary labels. The v2.0 goal is to
evolve it into a containerized, explainable, modular diagnostic platform with
honest model promotion criteria.

The core design philosophy does not change:
- **Physics and ML make the decisions.** LLMs only explain and orchestrate.
- **Rules + causality before statistics.** The CITA policy is never bypassed.
- **Honest metrics only.** No inflation, no stale numbers.

---

## v2.0 Target Architecture

```
ardupilot-diagnosis-platform/
├── docker-compose.yml
├── core-engine/          ← rule engine + tabular ML + IsolationForest
├── temporal-layer/       ← HMM + Kalman filter for noise filtering & sequence detection
├── causal-arbitrator/    ← Enhanced CITA + modular rule engine
├── llm-orchestrator/     ← LangGraph + local/API LLM (explanation, chat, workflow only)
├── feature-store/        ← Shared feature engineering (94+ features, Parquet, DuckDB)
├── report-service/       ← PDF/HTML/JSON generation + rich visuals
├── tuning-advisor/       ← PID ratings, vibration attribution, filter suggestions
├── multi-flight-analyzer/← Trend & degradation analysis across multiple logs
├── web-gateway/          ← FastAPI + modern frontend (unified UI)
└── data-pipeline/        ← Log ingestion, Parquet storage, DuckDB queries
```

**Why containerized microservices:**
- Any service can fail independently without killing the whole system.
- Each component can be upgraded (or replaced with a better model) without risk.
- Easy to open-source individual services separately if needed.
- LLM and ML concerns remain physically separated in code and runtime.

---

## Milestone 0 — Foundation & Containerization

**Goal:** Turn the existing monorepo into a clean, containerized platform.

**Status:** 🟨 Core container complete; feature-store/data-pipeline/gateway remain deferred

### Tasks

- [x] Write `docker-compose.yml` with a default core profile and explicit optional profiles.
- [x] Harden the core engine container and add healthchecks.
- [ ] Create a separate `feature-store` service (deferred; core extraction is in-process).
- [ ] Set up a `data-pipeline` service with Parquet storage + DuckDB querying.
- [ ] Create a real `web-gateway` reverse proxy (the current profile is a placeholder).
- [x] Update `.github/workflows/ci.yml` to validate the core and optional services.

### Deliverable

`docker compose up` starts the core engine with its healthcheck. The temporal
HMM and grounded explanation services are optional review-only containers and
must be enabled explicitly with `docker compose --profile experimental up`.
The nginx gateway remains a placeholder behind the `gateway` profile until a
real reverse-proxy configuration and TLS policy are supplied.

### Done when

- [x] Fresh clone + `docker compose up` starts the core engine with no manual steps.
- [x] The full local suite passes (338 tests; container execution remains a CI check).

---

## Milestone 1 — Temporal Layer

**Status:** 🟨 Optional review-only service; not part of the default core path

The temporal service is available behind the `experimental` Compose profile.
It requires an explicitly trained HMM and returns `503` until a model is ready;
it must not silently alter the core diagnosis.

### Deliverable

`temporal-layer` container available. `core-engine` can optionally call it before running XGBoost.
Benchmark shows improved precision on logs with known transient noise.

### Done when

- [ ] Temporal filter reduces false positives on at least 3 known noisy test logs.
- [ ] HMM training script is documented and reproducible.

---

## Milestone 2 — LLM Orchestration Layer

**Goal:** Add a natural language explanation and chat layer on top of the diagnostic engine.

**Status:** ⬜ Not started

### Philosophy

**The LLM never makes diagnostic decisions.** It only:
1. Converts structured diagnosis output into human-readable reports.
2. Answers user questions like "Why did EKF spike at 47s?" using the diagnosis context.
3. Orchestrates multi-step analysis workflows (e.g., "analyze, then generate PDF, then summarize").
4. Generates hypotheses for human review — clearly labelled as unverified.

This is explicitly **not** LLM-based fault detection. Physics and ML stay in control.

### Tasks

- [ ] Create `llm-orchestrator/` service using LangGraph for structured workflow management.
- [ ] Support two LLM backends: local (Ollama) and API (Groq / OpenAI).
- [ ] Build prompt templates that inject structured diagnosis JSON and ask for explanation only.
- [ ] Expose a `/explain` endpoint: takes a `DiagnosisResult`, returns natural language report.
- [ ] Expose a `/chat` endpoint: stateful Q&A about the current diagnosis.
- [ ] Add a "hypothesis mode" that generates alternative explanations — clearly marked as LLM-generated.
- [ ] Integrate with `report-service` to produce PDF/HTML reports with both technical + narrative sections.

### Deliverable

A chat interface in the web UI where users can upload a `.BIN` file, get a diagnosis,
then ask follow-up questions in plain English.

### Done when

- [ ] `/explain` endpoint produces a correct, grounded explanation for `vibration_high` on `sample.bin`.
- [ ] LLM output never contradicts the structured diagnosis from `core-engine`.
- [ ] Local (Ollama) path works without any external API keys.

---

## Milestone 3 — Unified Diagnostic Engine

**Goal:** Merge the core engine + temporal layer + causal arbitrator into a single, coherent pipeline.

**Status:** ⬜ Not started

### Tasks

**Rule Engine Refactoring (from open issues):**
- [ ] Break `src/diagnosis/rule_engine.py` into `src/diagnosis/rules/` modules:
  - `vibration.py`, `compass.py`, `power.py`, `gps.py`, `motors.py`
  - `ekf.py`, `mechanical_failure.py`, `pid_tuning.py`
  - `rc_failsafe.py`, `thrust_loss.py`, `brownout.py`, `crash_unknown.py`
- [ ] Add `tests/test_diagnosis_rules.py` with threshold boundary tests for every rule.

**Dead Label Remediation:**
- [ ] Add ML + rule coverage for: `power_instability`, `pid_tuning_issue`, `motor_imbalance`,
  `thrust_loss`, `gps_glitch`, `battery_failsafe`, `rc_failsafe`, `brownout`.
- [ ] Verify and fix `check_compass` rule — reduce reliance on ML fallback.

**Scaler Alignment:**
- [ ] Align the IsolationForest "healthy-only" scaler with the XGBoost "full-dataset" scaler.
  Document the decision or unify them.

**ML Artifacts:**
- [ ] Write `models/manifest.json` with: model version, feature schema hash, label schema hash,
  training dataset id, calibration date, threshold config hash.
- [ ] Add missing-artifact, schema-mismatch, and corrupted-model fallback tests.

### Deliverable

Single `/analyze` endpoint returns richer results with temporal smoothing, modular rule output,
and full 14-label coverage. All results traceable to physics evidence.

### Done when

- [ ] All 14 `VALID_LABELS` have at least one rule or ML path that can trigger them.
- [ ] No rule change requires editing a file longer than 200 lines.

---

## Milestone 4 — Advanced Capabilities

**Goal:** Build the features that make this platform irreplaceable.

**Status:** ⬜ Not started

### Tasks

**Multi-Flight Trend Analysis:**
- [ ] Create `multi-flight-analyzer/` service.
- [ ] Accept multiple `.BIN` files or a folder; detect degradation trends across flights.
- [ ] Output: trend plots (vibration over 10 flights, battery health curve, motor current drift).

**Tuning Advisor:**
- [ ] Create `tuning-advisor/` service.
- [ ] Rate PID parameters against the BASiC dataset baseline.
- [ ] Attribute vibration sources (motor, prop, frame resonance).
- [ ] Suggest notch filter center frequencies from FFT peaks.

**Report Service:**
- [ ] Create `report-service/` service.
- [ ] Generate PDF reports with: diagnosis summary, causal timeline, 3D trajectory, evidence panels.
- [ ] Generate structured JSON for external consumption (LLM agents, WebTools integration).

**CLI Refactoring (from open issues):**
- [ ] Break `src/cli/main.py` into `src/cli/commands/` modules:
  - `analyze.py`, `features.py`, `benchmark.py`, `batch_analyze.py`, `demo.py`
- [ ] `main.py` becomes a thin dispatcher only.

**Bad Input Handling (from open issues):**
- [ ] All batch, benchmark, and API endpoints handle empty/corrupt/partial `.BIN` files explicitly.
- [ ] Exit codes and error messages are consistent across all paths.

### Deliverable

Full platform — analyze, trend, tune, explain, export — all working end-to-end.

### Done when

- [ ] A user can upload 10 flights, get a degradation trend report, and receive a tuning recommendation.

---

## Milestone 5 — Production Hardening & v2.0 Release

**Goal:** Make the v2.0 platform release-ready for public use.

**Status:** ⬜ Not started

### Tasks

- [ ] Comprehensive test coverage: unit + integration + real crash log regression tests.
- [ ] Performance optimization: keep `/analyze` under 500ms on a standard log.
- [ ] All Docker images published to GitHub Container Registry.
- [ ] `docker compose up` documented as the one-line setup path.
- [ ] Updated model card, architecture doc, output formats doc.
- [ ] CHANGELOG updated to v2.0.
- [ ] README updated to reflect v2.0 capabilities.
- [ ] Release tag `v2.0.0` created on GitHub.

### Deliverable

Public v2.0 release. Anyone can run `docker compose up` and get a working instance.

### Done when

- [ ] All release gates from v1.0 still pass.
- [ ] Docker image size is reasonable (< 2GB).
- [ ] `README.md` accurately describes the v2.0 platform with no contradictions.

---

## Milestone 6 — Community Integration & Upstream Adoption

**Goal:** Get this adopted as a recognized ArduPilot community tool.

**Status:** ⬜ Not started

### Tasks

- [ ] Write a technical blog series covering: architecture decisions, CITA policy, temporal layer,
  LLM-as-orchestrator philosophy.
- [ ] Post the v2.0 release to the ArduPilot Discuss forum with a demo video.
- [ ] Investigate integration with MAVProxy and ArduPilot WebTools.
- [ ] Create a contribution guide for adding new rules, labels, and crash log datasets.
- [ ] Publish Docker images to Docker Hub for easy discoverability.
- [ ] Submit as a candidate for official ArduPilot tooling.

### Deliverable

ArduPilot community recognizes this as the best open-source log diagnosis platform.

---

## Current Prototype Status

Before starting v2.0, use the following as the honest baseline:

| Component | Status |
|---|---|
| Rule + tabular ML + IsolationForest | ⚠️ Offline prototype; candidate promotion blocked by release gates |
| Causal temporal arbitration | ✅ Deterministic heuristic, not a trained temporal model |
| 3D interactive flight replay | ✅ Working |
| Pre-flight parameter validation | ✅ Working |
| FastAPI web endpoint | ✅ Working |
| CLI | ✅ Working |
| Test suite | ✅ Regression suite required before every release |
| Candidate macro F1 | ⚠️ 0.500 on 23 grouped holdout incidents; release gate is 0.70 on 50+ |
| Incident calibration (ECE) | ⚠️ 0.153; release gate is ≤0.10 |
| Label coverage | ⚠️ Rules cover 14 types; ML is trained for 9 |
| Compass rule | ✅ Deterministic evidence plus ML where supported |
| Docker / containerization | ✅ Core image hardened; optional services are profile-gated |
| LLM explanation layer | 🟨 Grounded deterministic explanation service; optional/review-only |
| Temporal HMM layer | 🟨 Optional service; requires a trained artifact |
| Multi-flight analysis | ❌ Not yet |
| Tuning advisor | ❌ Not yet |

---

## Recommended Execution Order

1. **Milestone 0** — Containerize first. Safety net before touching anything.
2. **Milestone 1** — Temporal layer. Fastest improvement to diagnostic quality.
3. **Milestone 3 (Rule Engine only)** — Clean up the rule engine in parallel.
4. **Milestone 2** — LLM layer. High user-facing value, low risk (rules still decide).
5. **Milestone 3 (Dead Labels + Scalers)** — Complete after LLM layer is working.
6. **Milestone 4** — Advanced features once the core is solid.
7. **Milestone 5** — Harden and release.
8. **Milestone 6** — Community adoption.

---

## One-Line Rule

Do not add flashy new features on top of a broken foundation.
Earn the reputation by making what exists clean, reproducible, honest, and hard to break.
Then build upward from a position of strength.
