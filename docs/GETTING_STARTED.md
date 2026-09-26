# Getting Started with ArduPilot Log Diagnosis

This tool reads the flight logs your drone writes and tells you *what probably went wrong* after a crash. It is a read-only helper: it opens your log, looks for the earliest signs of trouble, and suggests candidate causes with the evidence behind each one. It is built for drone hobbyists, students, and new contributors who want help understanding a log without being ArduPilot experts. It accepts ArduPilot `.BIN`/`.LOG` logs, plus optional PX4 ULog, MAVLink TLog, and Betaflight Blackbox files. **Be clear about what it gives you: a triage hypothesis for human review, not a verified root cause** — you stay in charge of the final call. It never changes your drone's settings or your log files.

**Who should read this**
- A drone hobbyist who just crashed and wants to understand the log.
- A student or new contributor exploring the project for the first time.
- Anyone who has a `.BIN` file and does not know where to start.

**What you'll be able to do after this guide**
- Install the tool on Windows or Linux/macOS.
- Run a demo with no log file at all.
- Analyze your own flight log and read the result.
- Open the web dashboard.
- Understand what each result does — and does not — mean.

---

## 1. What this tool does (and why)

A single ArduPilot flight log can hold thousands of telemetry messages across dozens of subsystems. When a drone crashes, working out *why* by hand takes expert knowledge of ArduPilot internals and hours of squinting at graphs. The final visible failure (say, an EKF problem) is often not the real cause — something like heavy vibration may have started the chain seconds earlier. This is the difference between a **symptom** and a **root cause**.

This tool automates the boring part. It parses the log, extracts a fixed set of measurements, runs hand-written rules plus a trained model, and returns a ranked list of **evidence-backed candidate causes** — not a verdict. For each candidate you get the evidence that supports it, a plain recommendation, and a quality/coverage status so you know how much to trust it. When the log is too thin to support a reliable claim, the engine **abstains** and tells you a human should review it.

What you get, in plain words: a short report that says "here are the most likely causes, in order, with the reasons, and here is where the tool is not sure."

---

## 2. Words you'll see (plain-English glossary)

| Term | What it means in plain words |
|---|---|
| **ArduPilot** | Open-source autopilot firmware that flies drones, planes, rovers, and boats. This tool diagnoses logs from ArduPilot vehicles. |
| **DataFlash log** | ArduPilot's on-board flight recorder. It saves thousands of timestamped telemetry messages (vibration, compass, GPS, battery, motors, EKF, and more). |
| **.BIN / .LOG file** | The two DataFlash file types: `.BIN` is the binary version, `.LOG` is the text version. This is the tool's main input. |
| **PX4 ULog** | The log format of PX4, a *different* autopilot firmware. Accepted through a generic adapter. |
| **MAVLink TLog** | A telemetry log recorded over the MAVLink radio protocol — what your ground station saw during flight. Accepted through a generic adapter. |
| **Betaflight Blackbox** | The log format from Betaflight/Cleanflight (FPV and racing drones). Optional, and needs an extra install. |
| **Root cause vs symptom** | Symptom = the final visible event (e.g. an EKF failure or a power drop). Root cause = the earliest thing that physically started the chain (e.g. vibration 30 seconds earlier). The project's policy is "earliest onset wins." |
| **Rule engine** | 13 hand-written if/then checks based on ArduPilot knowledge, e.g. "vibration above a threshold → vibration_high." No machine learning involved. |
| **ML classifier** | A trained statistical model (the runtime artifact is a RandomForest) that predicts a cause from the extracted measurements. It only loads if its saved data schema matches the current runtime. |
| **Anomaly detector** | A model trained only on healthy flights. It flags telemetry that looks unusual, to catch problems the fixed rules do not cover. |
| **Hybrid engine** | The part that merges the rule findings, the ML scores, the anomaly signals, and the time-based arbitration into one ranked list of hypotheses. |
| **CITA (Crash-Immune Temporal Arbitration)** | The project's method for ignoring post-crash noise: each measurement records the exact time it first crossed a threshold, candidates are sorted by that time, and signals that only appear *after* impact are filtered out. **Measured status: it currently shows no measurable benefit** on the available data. |
| **111 features** | The fixed list of 111 numbers the tool computes from a log (max vibration, battery voltage range, motor spread, EKF variance, etc.). Both the rules and the ML model read these numbers. |
| **Abstention / uncertain** | When evidence is weak, the tool refuses to confirm. It returns the state `uncertain` — "requires human review" — instead of `confirmed`. |
| **Benchmark** | A fixed set of real logs with known answers, used to score the tool honestly. Sizes: v1 = 41 logs from 37 incidents; v2 = 22 logs from 21 incidents; v3 = 34 logs from 32 incidents. |
| **Leakage** | When the same flight (or incident) ends up in both the training and test data, making the tool look far better than it really is. |
| **Incident-grouped evaluation** | Splitting the data so that every log from one incident stays entirely on one side. This is the honest alternative to a random split. |
| **macro-F1** | A single 0-to-1 score (higher is better) that averages accuracy equally across all failure classes, so rare classes count as much as common ones. |
| **Chance baseline** | The score you would get simply by guessing. Used to check whether the tool has any real skill. |
| **Evidence ledger** | A register that lists every published performance number together with the artifact, the one command that regenerates it, and the commit. Rule: "A number without a complete row is not a result." |
| **Pre-registration** | Writing down the evaluation plan (data, metric, hypotheses) and committing it *before* seeing results, so the goalposts cannot move. |
| **SHA256** | A fingerprint of a file's exact bytes. Used to detect duplicate logs and give each log a verifiable identity. |
| **Provenance** | The documented origin of a log — which forum thread or GitHub issue it came from, and who diagnosed it. |

---

## 3. Before you start (prerequisites)

- **Python 3.10+** — the tool is written in Python and requires at least version 3.10.
- **pip** — the package installer that ships with Python; it installs the tool's dependencies.
- **git** — used only to download (clone) the repository once.
- **No internet needed after install** — once the dependencies are installed, analysis runs fully offline on your machine.

---

## 4. Setup, step by step

### (a) Windows (PowerShell)

1. **Clone the repository and enter the folder.**
   ```powershell
   git clone https://github.com/BeastAyyG/ardupilot-log-diagnosis.git
   cd ardupilot-log-diagnosis
   ```
   *Why:* downloads the project and puts you inside its folder so later commands run from the right place.

2. **Create a virtual environment.**
   ```powershell
   python -m venv .venv
   ```
   *Why:* creates an isolated space (`.venv`) so this tool's packages do not clash with other Python projects.

3. **Activate it.**
   ```powershell
   .venv\Scripts\Activate.ps1
   ```
   *Why:* switches your terminal to use that isolated space.

4. **Install the tool and its dev dependencies.**
   ```powershell
   pip install -e ".[dev]"
   ```
   *Why:* installs this project in editable mode (`-e`) along with the extra packages the `[dev]` group needs (tests, the web server, and so on). Be aware that this install is fairly large — `[dev]` also pulls in training and plotting libraries such as xgboost, lightgbm, and matplotlib — so the first install may take several minutes and use a few hundred MB; that is expected, not a problem.

### (b) Linux / macOS (bootstrap script)

1. **Clone the repository and enter the folder.**
   ```bash
   git clone https://github.com/BeastAyyG/ardupilot-log-diagnosis.git
   cd ardupilot-log-diagnosis
   ```
   *Why:* same as above — get the code and stand in its folder.

2. **Run the one-click setup.**
   ```bash
   ./bootstrap.sh setup
   ```
   *Why:* creates the virtual environment, activates it, upgrades pip, and runs `pip install -e ".[dev]"` for you. (The script uses `python3` and POSIX paths, so it is for Linux/macOS only.)

Handy bootstrap shortcuts once set up: `./bootstrap.sh demo`, `./bootstrap.sh analyze flight.BIN`, `./bootstrap.sh test`, `./bootstrap.sh lint`.

---

## 5. Your first analysis, step by step

### (a) Run the built-in demo (no log needed)

```bash
python -m src.cli.main demo
```
*Why:* cements the install by running the whole pipeline on a bundled sample, so you can see the output shape before touching a real file. The repo ships `sample.bin` and `test_cascade.BIN` for exactly this. Expect a text report: log metadata, an ordered list of candidate causes with evidence, and a decision status.

### (b) Analyze a real log

```bash
python -m src.cli.main analyze path/to/your/flight.BIN
```
*Why:* runs the real diagnosis on your own log. You get candidate causes in order of likelihood, each with the evidence that supports it and a recommendation. Add `--nexus` (a read-only extra that adds causal-order evidence to the report) for extra CITA-Nexus causal evidence.

### (c) Optional: save an HTML report

```bash
python -m src.cli.main analyze flight.BIN --format html -o report.html
```
*Why:* turns the same result into a shareable HTML file you can open or send to someone.

### (d) Launch the dashboard

```bash
python -m src.cli.main ui
```
Then open **http://localhost:8000** in your browser. *Why:* gives you a visual view — drag-and-drop upload, a 3D flight path, a crash timeline, and an "AI Integrity Report" that compares the rule engine against the hybrid result.

**Reading the result.** Each candidate is a hypothesis with supporting evidence — not a confirmed verdict. If a result is marked **uncertain / requires human review**, it means the tool abstained: the evidence was too weak (low confidence, two close candidates, or a single-model result) to confirm safely. That is a feature, not a failure — it keeps the tool from sounding sure when it is not.

---

## 6. Supported log formats

| Format | Extensions | Notes |
|---|---|---|
| ArduPilot DataFlash | `.BIN`, `.LOG` | Primary format; all ArduPilot checks apply. |
| PX4 ULog | `.ULG`, `.ULOG` | Generic adapter; not validated as equivalent to ArduPilot diagnosis. |
| MAVLink TLog | `.TLOG` | Generic adapter; captures what the ground station saw. |
| Betaflight Blackbox | `.BBL`, `.BFL` | Optional; requires the extra install below. |

For Betaflight Blackbox support, the README documents:

```bash
pip install -e ".[blackbox]"
python -m src.cli.main analyze flight.bbl --format json
```

> **Heads-up:** this `blackbox` extra is documented in README.md but is **not defined in `pyproject.toml`** (which only lists `dev`, `web`, and `forum`). The Blackbox adapter needs the third-party `orangebox` package. Because the extra is missing, the install command above **may fail** — do not assume it works without checking first.

---

## 7. Troubleshooting

- **"Command not found" or files not found.** Make sure you are running commands from the **repository root** (the folder you cloned into), and that your virtual environment is activated. Paths like `flight.BIN` are relative to where you stand.
- **Tests look like they fail on Windows.** Some failures under a sandboxed Windows shell are artifacts of a sandbox file-deletion guard, **not real product bugs**, and they pass when run in isolation. See `docs/TESTING.md` for how to get a trustworthy result. Do not hard-code a test count — **CI is authoritative.**
- **Dashboard will not start.** If **port 8000 is already in use**, close whatever is using it, or stop the other instance of the dashboard, then run `python -m src.cli.main ui` again.
- **Betaflight install fails.** See the Heads-up in Section 6: the `[blackbox]` extra is not defined in `pyproject.toml`.

---

## 8. What the results mean (read this)

This is the most important section. The tool is a **diagnostic aid**, and the project says so plainly in `docs/model_card.md`:

> "A label returned by the hybrid engine is a triage hypothesis, not a verified root cause."

> "It is not approved for autonomous flight decisions or unsupervised maintenance decisions."

There are three decision states:

- **healthy** — no significant anomalies were detected.
- **uncertain (requires human review)** — too weak, too close, or too single-sourced to confirm. A human should look.
- **confirmed** — a high-confidence, clearly separated top candidate.

Even a *confirmed* result is a strong hypothesis, not a guarantee. Treat every diagnosis as something to review against the evidence and your own knowledge of the flight.

---

## 9. Where to go next

- [Testing guide](TESTING.md) — how to run the test suite and read its output.
- [Evidence ledger](EVIDENCE_LEDGER.md) — every published number, its artifact, and its reproduction status.
- [Publication plan](PUBLICATION_PLAN.md) — the roadmap to a reproducible benchmark and paper.
- [Root-cause labeling policy](root_cause_policy.md) — the authoritative "earliest onset wins" standard.
- [Contributing](../CONTRIBUTING.md) — how to submit crash logs or add diagnosis rules.
