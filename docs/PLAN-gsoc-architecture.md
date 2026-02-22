# Project Plan: ArduPilot AI Log Diagnosis (GSoC)

## 1. Overview
This project involves building a comprehensive, AI-assisted log diagnosis tool for ArduPilot's `.BIN` flight logs. The goal is to extend the existing rule-based prototype into a hybrid rule-and-ML-based diagnosis engine over the 12-week GSoC period. It will parse logs, extract 60+ numerical features, detect failures (mechanical, EKF, etc.), reference known forum cases, and output actionable reports.

## 2. Project Type
**BACKEND** (Data Processing, CLI Tool, ML Pipeline)

## 3. Success Criteria
- [ ] Parses ArduPilot `.BIN` files in <2-3 seconds.
- [ ] Extracts 60+ features robustly (handling missing messages).
- [ ] Employs a Hybrid Diagnosis Engine (Rules + XGBoost) parsing in <100ms.
- [ ] Successfully performs cosine similarity search via the Retrieval Engine.
- [ ] Outputs structured JSON and human-readable terminal reports.
- [ ] Provides a comprehensive test suite (unit and integration tests).

## 4. Tech Stack
- **Language**: Python 3.8+
- **Core Processing**: `pymavlink` (BIN parsing), `numpy`
- **Machine Learning**: `scikit-learn` (baseline, standard scaler), `xgboost` (multi-label classifier)
- **Data & Training**: `pandas`, `matplotlib`, `scipy` (for FFT features)
- **Configuration**: `pyyaml`
- **Testing**: `pytest`

## 5. File Structure
Target structure defined in architecture document:
```
ardupilot-log-diagnosis/
├── src/
│   ├── parser/
│   ├── features/
│   ├── diagnosis/
│   ├── retrieval/
│   ├── reporting/
│   └── integration/
├── models/
├── training/
├── tests/
└── docs/
```

## 6. Task Breakdown

| Task ID | Name | Agent | Skills | Priority | Dependencies | INPUT → OUTPUT → VERIFY |
|---------|------|-------|--------|----------|--------------|-------------------------|
| T1 | **Scaffold Project Structure** | `backend-specialist` | `python-patterns` | P0 | None | IN: None → OUT: Folder structure, `__init__.py` files, `requirements.txt` → VERIFY: Directory tree matches spec |
| T2 | **Module 1: Log Parser** | `backend-specialist` | `python-patterns` | P0 | T1 | IN: `.BIN` log → OUT: Structured dictionary of messages & metadata → VERIFY: Passes `test_parser.py` |
| T3 | **Module 2: Feature Pipeline Base** | `backend-specialist` | `python-patterns` | P1 | T2 | IN: MAVLink dict → OUT: 37+ numerical features via extractors → VERIFY: No missing/NaN feature errors |
| T4 | **Module 2: Advanced Features** | `backend-specialist` | `python-patterns` | P1 | T3 | IN: EKF/IMU messages → OUT: FFT and EKF metrics (60+ total) → VERIFY: FFT metrics output correctly |
| T5 | **Module 3: Rule Engine** | `backend-specialist` | `clean-code` | P1 | T3 | IN: Feature dict → OUT: RuleDiagnosis alerts & confidence → VERIFY: Flags known bad parameters correctly |
| T6 | **ML Pipeline & Classifier** | `backend-specialist` | `python-patterns` | P1 | T4 | IN: `features.csv`, `labels.csv` → OUT: Trained XGBoost model & Scaler → VERIFY: >85% accuracy on test set |
| T7 | **Module 3: Hybrid Engine** | `backend-specialist` | `clean-code` | P2 | T5, T6 | IN: Rule + ML results → OUT: Merged confidence array → VERIFY: Sorting and boosting logic works |
| T8 | **Module 4: Retrieval Engine** | `backend-specialist` | `python-patterns` | P2 | T3 | IN: Target feature vector → OUT: Top-3 similar forum cases → VERIFY: Matches identical files at 100% |
| T9 | **Module 5 & 6: Reporting and CLI** | `backend-specialist` | `python-patterns` | P2 | T7, T8 | IN: Final diagnoses → OUT: JSON file & terminal breakdown → VERIFY: CLI arguments function correctly |
| T10 | **Testing & Documentation** | `test-engineer` | `testing-patterns` | P3 | All | IN: src/ → OUT: `pytest` suite and READMEs → VERIFY: 100% test pass rate |

## 7. Phase X: Verification Checklist
- [ ] **Linting:** Run `flake8` or `pylint` to ensure codebase meets standards.
- [ ] **Unit Tests:** Execute `pytest` ensuring `test_parser`, `test_features`, `test_diagnosis`, `test_retrieval`, and `test_integration` pass.
- [ ] **Integration Tests:** Verify full pipeline (`.BIN` → parsing → output).
- [ ] **Socratic rules check:** Verified structure and logic.
- [ ] **ML Check:** Run cross-validation manually on dataset.

## 8. Data Provenance and Curation
- Legacy companion-health artifacts are migrated into `companion_health/data/health_monitor/`.
- Companion-health dataset quality is validated through
  `companion_health/scripts/integrate_legacy_health_monitor.py` with:
  - schema checks,
  - class-balance checks,
  - duplicate detection,
  - numeric range reporting.
- Companion-health data remains separate from diagnosis benchmark labels.
- Ground-truth metadata is synchronized by `training/refresh_ground_truth_metadata.py`.
- Project boundary validation is enforced by `training/validate_project_boundaries.py`.
- Training dataset generation supports confidence-based filtering via
  `python training/build_dataset.py --min-confidence <level>`.
- External benchmark batches can be clean-imported with
  `python -m src.cli.main import-clean --source-root <path> --output-root <path>`.
- Clean import emits immutable provenance artifacts (inventory, rejected files,
  hash-based dedupe manifest, benchmark-ready ground truth subset).
