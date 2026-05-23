# Contributing to ArduPilot AI Log Diagnosis

Thank you for your interest in improving ArduPilot flight safety tooling. There are three primary ways to contribute:

---

## 1. 📁 Contributing Crash Logs

High-quality, expert-labeled crash logs are the fuel for this project. We accept logs that meet all of the following criteria:

| Requirement | Detail |
|---|---|
| **Source** | Must link to a public ArduPilot forum thread (`discuss.ardupilot.org`) |
| **Expert Diagnosis** | Thread must contain a Developer or experienced maintainer diagnosis comment |
| **File Format** | ArduPilot `.BIN` dataflash format only |
| **No SITL Logs** | Simulator (SITL) logs are excluded from the production benchmark |
| **Root Cause Known** | Label must align with the **Root-Cause Precedence policy** (see below) |

### Root-Cause Labeling Policy
We label the **earliest telemetry anomaly** (`tanomaly`), not the final symptom. Examples:
- Vibration (80 m/s² peaks) → EKF failure → crash: label `vibration_high`, not `ekf_failure`.
- Compass EMI spike → yaw reset → crash: label `compass_interference`.
- If two causes onset within 5 seconds, the rule with highest confidence score wins.

### Valid Labels
`vibration_high` · `compass_interference` · `ekf_failure` · `motor_imbalance` · `power_instability` · `gps_quality_poor` · `pid_tuning_issue` · `rc_failsafe`

### How to Submit
1. Add forum thread URL + download URL to `download_logs.md` under the appropriate label.
2. Run the clean import pipeline to validate and ingest:
   ```bash
   python -m src.cli.main import-clean \
     --source-root /path/to/your/logs \
     --output-root data/clean_imports/my_contribution
   ```
3. Verify the provenance proof was generated: `data/clean_imports/my_contribution/manifests/provenance_proof.md`.
4. Open a Pull Request attaching the `provenance_proof.md` as evidence.

---

## 2. ⚙️ Contributing Diagnosis Rules

The rule engine lives in `src/diagnosis/rule_engine.py`. Rules follow a tested, threshold-driven pattern aligned with `models/rule_thresholds.yaml`.

### Rule Checklist
- [ ] Rule targets exactly one `VALID_LABEL` from `src/constants.py`.
- [ ] Threshold values are defined in `models/rule_thresholds.yaml` (not hardcoded).
- [ ] Rule fires on the correct message family (check `src/features/` for feature names).
- [ ] A unit test in `tests/test_diagnosis.py` verifies it fires on a known-bad feature set and does NOT fire on a healthy feature set.
- [ ] Evidence dict returned contains `feature`, `value`, `threshold`, and `context` keys.
- [ ] Recommendation returned contains `first_checks` list and `next_steps` list.

### Run the Full Test Suite Before Opening a PR
```bash
pytest -q
python training/validate_project_boundaries.py
```

---

## 3. 🧪 Running the Test Suite

```bash
# Full suite (56 tests)
pytest -q

# Only diagnosis tests
pytest tests/test_diagnosis.py -v

# Only parser tests
pytest tests/test_parser.py -v
```

All 56 tests must pass. The CI workflow enforces this on every push and pull request.

---

## Code Style

- Python 3.10+. Type annotations on all public functions.
- Line length: 100 characters. Run `ruff check .` before committing (`.ruff_cache` is present).
- No fabricated labels, no hardcoded file paths — use constants from `src/constants.py`.

---

## Questions?

Open a GitHub Issue with the `question` label, or refer to [`AGENTS.md`](AGENTS.md) for a full picture of the project's goals and operating policy.

---

## Log File Handling

Large binary `.BIN` log files should not be committed directly to the repository.
They are marked as binary in `.gitattributes` to avoid large diffs.
Small sample logs for testing are permitted in the `tests/` directory.

---

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).
By participating, you are expected to uphold this code.

If you witness or experience unacceptable behavior, please report it by contacting the maintainer privately via GitHub or email.
