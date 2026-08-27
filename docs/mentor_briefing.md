# CITA‑Nexus — Mentor Briefing (Zero‑Explanation Flowchart Pack)

> **Audience:** AI/ML‑literate mentor (strong on model training, less familiar with the
> drone‑log domain or this repo's internal architecture).
> **Goal:** After reading this single document you should understand the *whole* project,
> the *model we actually built*, *why accuracy is where it is*, and *how it is deployed/costed* —
> without any further back‑and‑forth.
> **Repo:** `ardupilot-log-diagnosis` (codename **CITA‑Nexus**), MIT, GSoC 2026 candidate.

---

## 0. TL;DR (read this first)

We built an **automated root‑cause diagnostic engine for ArduPilot drone flight logs**
(`.BIN` DataFlash telemetry). A pilot hands over a crashed/failed flight log; the system
returns *what broke, when, why, and how to fix it* — in under 250 ms on CPU.

It is **NOT** a VLA (Vision‑Language‑Action) model. It is a **small, edge‑deployable
ML classifier** ("SLM‑class" in size) built on top of a **deterministic physics rule engine**.
Think: a tiny gradient‑boosted tree model that consumes a vector of physics/engineering
features — not a billion‑parameter LLM. That is why it fits on a phone and runs on cheap CPU.

**Current state:** held‑out **macro‑F1 ≈ 0.50**. Hard requirement for safe deployment is
**≥ 0.70** (ideally 0.80), because *below ~0.70 the model is net‑harmful* — it mis‑diagnoses
and can worsen a drone's setup more than leaving it alone.

---

## 1. Master End‑to‑End Flow

```mermaid
flowchart TD
    subgraph SRC[Data Sources]
        A1["Real flight logs<br/>(.BIN from forums / field /<br/>expert‑labeled incident pool)"]
        A2["Synthetic logs<br/>(SITL fault‑injection sims<br/>~250+ generated)"]
    end

    A1 --> ING
    A2 --> ING

    subgraph PIPE[Core Engine — CITA‑Nexus]
        ING["① Ingestion<br/>Zero‑copy Apache Arrow decode<br/>+ PCHIP 50Hz resample"]
        FEAT["② Feature Engineering<br/>6‑DOF physics residuals ·<br/>44‑rule matrix · Welch FFT ·<br/>Wiener PID → fixed‑len vector"]
        HYB["③ Hybrid Arbiter<br/>Rule Engine (deterministic)<br/>+ ML Classifier (probabilistic)"]
        REM["④ Remediation<br/>Safe param deltas<br/>(±25% clamp, critical‑lock)"]
        OUT["⑤ Interfaces<br/>CLI · 3D WebGL · MCP server"]
    end

    ING --> FEAT --> HYB --> REM --> OUT

    HYB -->|"predicted failure class<br/>+ calibration (ECE)"| TRAIN((Model Artifacts<br/>classifier.joblib<br/>scaler.joblib))

    subgraph DEP[Deployment / Cost]
        D1["CPU instance (AWS / RunPod / Vast)<br/>$2–10k/mo AWS → ~50% cheaper off‑AWS"]
        D2["Edge / Phone (small model)<br/>via on‑device sim inference"]
    end

    OUT --> D1
    OUT --> D2
    TRAIN -.-> D1
    TRAIN -.-> D2
```

**Why this shape:** the deterministic rule engine guarantees *zero false‑alarm* on the
post‑crash impact shock (a classic ML trap), while the ML layer catches the *subtle,
multi‑signal* failures rules miss. They arbitrate, they don't replace each other.

---

## 2. Data Generation (where the 250 sims come from)

This is the part most people get wrong about the project. **We do not have 1M real
crashed logs.** We *manufacture* labeled training data two ways:

```mermaid
flowchart LR
    subgraph REAL[Real Data — scarce & expensive]
        R1["Mine forums / field logs<br/>(ArduPilot Discourse, etc.)"]
        R2["Expert‑label mining<br/>(140 → 500+ verified incidents)"]
        R3["(Optional) real telemetry<br/>uploads from users"]
    end

    subgraph SYN[Synthetic Data — our volume engine]
        S0["SITL = Software‑In‑The‑Loop<br/>(ArduPilot sim + firmware)"]
        S1["Fault injection:<br/>• SIM_ENGINE_FAIL (motor loss)<br/>• SIM_GPS_DISABLE (GPS denial)<br/>• SIM_BATT_VOLT (battery sag)"]
        S2["Headless parallel cluster<br/>generates ~250+ labeled .BIN logs"]
        S3["Each sim has a KNOWN ground‑truth<br/>failure label (cheap, perfect labels)"]
    end

    R1 --> POOL["Labeled Dataset<br/>(features.csv · labels.csv · groups.csv)"]
    R2 --> POOL
    R3 --> POOL
    S0 --> S1 --> S2 --> S3 --> POOL
```

**Key insight for the mentor:** synthetic data gives us *perfect labels for free*, but it
comes from a *simulator distribution*. That simulator gap is the single biggest reason our
**real‑world accuracy collapses to ~0.5** when the model meets logs it wasn't generated from
(the "0.5%" panic in our chat was test data drawn from a very different distribution than
training). This is a textbook **train/serve distribution shift**, not a model‑capacity problem.

---

## 3. Feature Engineering (the actual model input)

The classifier never sees raw bytes. It sees an engineered vector:

```mermaid
flowchart TD
    RAW["Resampled 50Hz multi‑stream tensor<br/>(IMU 400Hz, ATT 50Hz, GPS 5Hz, BAT 10Hz)"]
    --> P1["6‑DOF Inverse Dynamics<br/>τ_res = I·ω̇ + ω×(Iω) − M·u_motors<br/>→ force/torque residuals"]
    --> P2["44‑Rule Matrix (7 subsystems)<br/>Sensors · Power · Control ·<br/>Estimator · Mechanical · Nav · Firmware"]
    --> P3["Welch PSD → harmonic notch<br/>(INS_HNTCH_FREQ/BW)"]
    --> P4["Wiener PID deconvolution<br/>rise time · overshoot · ζ damping"]
    --> FV["Fixed‑length FEATURE VECTOR<br/>(feature_columns.json)<br/>+ StandardScaler"]
```

These features are what `train_model.py` and `ml_classifier.py` consume. The *same* vector
is produced at inference time from a real uploaded `.BIN`, so train/serve feature code is identical.

---

## 4. Model Architecture (what "the model" actually is)

```mermaid
flowchart TD
    FV["Feature vector x"] --> RULE["Deterministic Rule Engine<br/>(physics‑grounded, 0 false‑alarms<br/>on impact shock)"]
    FV --> ML["ML Classifier (small, tree‑based)"]

    subgraph MLDETAIL["ML Classifier family (sklearn / xgboost)"]
        M1["RandomForest (baseline)"]
        M2["XGBoost (tuned via GridSearchCV)"]
        M3["+ Isotonic Calibration (ECE)"]
        M4["Voting Ensemble<br/>RF + XGB + LGBM + ExtraTrees"]
    end

    ML --> MLDETAIL
    RULE --> ARB["Hybrid Arbiter<br/>(confidence‑gated fusion)"]
    M4 --> ARB
    ARB --> DEC["Decision: Healthy / Warning / Critical<br/>+ top root cause + confidence"]
    ARB -->|"low confidence on edge case"| ABSTAIN["Abstain → Rule‑Engine‑only<br/>(preserves diagnostic integrity)"]
```

**Size/complexity:** this is a **Small Model (SLM‑class)** — a few hundred KB joblib of
gradient‑boosted trees, not a transformer. That is the whole point of the "small model on
the phone" comment: it runs in milliseconds on a CPU, no GPU, no API call.

---

## 5. Training & Evaluation (the 0.50 → 0.70 problem)

This is the exact part of our chat ("80/20", "macro F1", "0.5 vs 0.5%"):

```mermaid
flowchart TD
    POOL["Labeled dataset<br/>(real + synthetic, with flight_id groups)"]
    --> SPLIT{"Split strategy"}

    SPLIT -->|"Simple view (what I told you)"| S8020["80 / 20 train–verify<br/>(classic holdout)"]
    SPLIT -->|"Rigorous view (what we actually use)"| SKF["StratifiedGroupKFold<br/>grouped by flight_id<br/>→ ZERO flight leakage"]

    S8020 --> TRAIN["Train classifier<br/>+ StandardScaler + calib"]
    SKF --> TRAIN

    TRAIN --> EVAL["Evaluate Macro‑F1<br/>(class‑balanced, not accuracy)"]

    EVAL --> ISO["Isolate two numbers:<br/>• Macro‑F1_real (physical logs)<br/>• Macro‑F1_synthetic (sims)"]
    ISO --> THR["Per‑class threshold tuning<br/>θ_c ∈ [0.10, 0.90]<br/>(stops rare classes → 0)"]

    THR --> CUR["CURRENT: Macro‑F1 ≈ 0.50<br/>TARGET: ≥ 0.70 (safe), 0.80 (ideal)"]
    CUR --> WHY["Below 0.70 ⇒ net‑harmful:<br/>mis‑diagnosis can BREAK the drone<br/>worse than no tool"]
```

**Why Macro‑F1 and not accuracy:** failure classes are heavily imbalanced (most flights are
"healthy"; a few failure modes are rare). Plain accuracy hides the fact that we predict
"healthy" all day. *Macro‑F1 weights every class equally* — that's the honest metric, and
it's why the bar is 0.70.

**Why 0.50 today:** (a) synthetic↔real distribution shift (Section 2), (b) rare classes
starved of real examples, (c) threshold/leakage still being tightened. The fix path is
*more diverse real labels + domain adaptation*, **not** a bigger model.

---

## 6. Deployment, Cost & "Small Model on Phone"

```mermaid
flowchart LR
    subgraph INFRA[Where it runs]
        C1["CPU instance 24/7<br/>AWS: ~$2–10k/mo (avg net)<br/>RunPod / Vast / Indian providers:<br/>~50% cheaper"]
        C2["Edge / Phone<br/>tiny joblib, on‑device sim<br/>handles simple problems"]
    end

    ART["classifier.joblib + scaler.joblib<br/>(few‑hundred‑KB, CPU‑only)"]
    --> C1
    ART --> C2

    C1 --> SRV["MCP JSON‑RPC server<br/>(Claude/Cursor/Agent access)<br/>+ batch CLI + 3D WebGL reports"]
    C2 --> APP["Field‑engineer app<br/>(offline, air‑gapped SVG reports)"]

    REF["Benchmark: Bharti Airtel deployed a<br/>Small AI Model to 30k field engineers<br/>→ ₹30–45 cr cost savings<br/>(same 'small model at the edge' thesis)"]
```

**Cost note (from our chat):** the model is *cheap to serve* precisely because it's small
and CPU‑bound. A 24/7 CPU box on AWS is the expensive end (~$2–10k/mo with networking);
RunPod/Vast/Indian providers roughly halve that. There is **no GPU bill**, no per‑token LLM
cost — that's the economic argument for an SLM over a hosted LLM/VLA.

---

## 7. Glossary — chat slang → technical term

| What I said in chat | Actual meaning in the repo |
|---|---|
| "generated this type of data" | SITL fault‑injection simulation logs (synthetic, perfectly labeled) |
| "CPU instance 2–10k" | 24/7 CPU serving cost; RunPod/Vast ~50% cheaper |
| "0.5 / 50%" | **Macro‑F1 ≈ 0.50** (not 0.5%) on held‑out data |
| "0.5% on 250 sims" | score collapsed to ~0.5% when test data was *very different* from generated data (distribution shift) |
| "80/20" | classic 80% train / 20% verify holdout (we also use StratifiedGroupKFold) |
| "macro f1 0.7" | safe deployment threshold (Macro‑F1 ≥ 0.70) |
| "SLM / small model / phone" | small tree‑based classifier, CPU/edge deployable, not an LLM |
| "na, not a VLA" | it is **not** a Vision‑Language‑Action model |
| "can break the drone" | below 0.70 macro‑F1 the model is net‑harmful (mis‑remediation) |
| "Airtel small AI model" | real‑world proof point for small‑model‑at‑the‑edge economics |

---

## 8. One‑Paragraph Explanation You Can Paste

> CITA‑Nexus is an automated root‑cause diagnostic engine for ArduPilot drone flight logs.
> We parse `.BIN` telemetry with a zero‑copy Arrow pipeline, engineer physics features
> (6‑DOF residuals, a 44‑rule matrix, spectral and PID analysis), and feed them to a **small
> hybrid model** = deterministic rule engine + a gradient‑boosted tree classifier (RandomForest/
> XGBoost/ensemble, ~few‑hundred‑KB joblib). Training data is mostly *synthetic* (SITL fault
> injection, ~250+ perfectly‑labeled logs) plus a smaller pool of real expert‑labeled incidents.
> We evaluate with **Macro‑F1 under StratifiedGroupKFold** (no flight leakage) and currently sit
> at ≈0.50; the safety bar is ≥0.70 because below that the model mis‑diagnoses and can damage the
> drone. It's deliberately **small and CPU/edge‑deployable** (phone, cheap RunPod/Vast instances),
> not a VLA or LLM — which is what makes it economical to run 24/7.

---

*Generated for mentor hand‑off. All diagrams are Mermaid and render on GitHub, VS Code, and
most Markdown viewers. No code was changed to produce this document.*
