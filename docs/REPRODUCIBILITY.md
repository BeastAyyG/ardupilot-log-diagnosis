# Reproducibility Guide

This document provides exact commands to set up, verify, and run the ArduPilot Log Diagnosis project from a fresh clone.

---

## Quick Start

### 1. Clone and Setup

```bash
# Clone the repository
git clone https://github.com/BeastAyyG/ardupilot-log-diagnosis.git
cd ardupilot-log-diagnosis

# Run setup (creates venv, installs dependencies)
./bootstrap.sh setup
```

### 2. Verify Installation

```bash
# Verify CLI help works
./bootstrap.sh demo

# Run tests
./bootstrap.sh test
```

### 3. Run a Demo

```bash
# Run the built-in demo (no real log required)
./bootstrap.sh demo
```

---

## Detailed Commands

### Setup

```bash
./bootstrap.sh setup
```

This will:
1. Create a virtual environment at `.venv/`
2. Install all dependencies from `pyproject.toml`
3. Install dev dependencies (linting, testing tools)

### Manual Setup (Alternative)

```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Verify
python -m src.cli.main --help
```

### Running Tests

```bash
# Run all tests
./bootstrap.sh test

# Run specific test file
./bootstrap.sh test tests/test_parser.py

# Run with verbose output
./bootstrap.sh test -v
```

### Running the Demo

```bash
# Terminal output
./bootstrap.sh demo

# HTML output
./bootstrap.sh demo --format html -o demo.html
```

### Analyzing a Log

```bash
# Analyze a real .BIN file
./bootstrap.sh analyze path/to/flight.BIN

# With JSON output
./bootstrap.sh analyze path/to/flight.BIN --json

# Rule-only mode (no ML)
./bootstrap.sh analyze path/to/flight.BIN --no-ml
```

### Running Benchmark

```bash
# Run default benchmark
./bootstrap.sh benchmark

# Run with custom dataset
./bootstrap.sh benchmark --dataset-dir data/clean_imports/.../dataset --ground-truth data/clean_imports/.../ground_truth.json
```

### Linting

```bash
./bootstrap.sh lint
```

---

## Requirements

- Python 3.10 or higher
- Linux/macOS (Windows support via WSL)

---

## Troubleshooting

### "command not found: pytest"

Run setup again:
```bash
./bootstrap.sh setup
```

### "ModuleNotFoundError: No module named 'pymavlink'"

The virtual environment may not be activated. Run:
```bash
source .venv/bin/activate
```

### Tests fail

Check that you're in the project root directory and the virtual environment is activated.

---

## CI Verification

The same setup path used here is used in CI (`.github/workflows/ci.yml`). If it works locally, it should work in CI.
