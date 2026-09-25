# 🚀 Project Antigravity: GSoC 2026 Roadmap

## Phase 1: Foundation (The Heavy Lift) - [DONE]
* [x] **Hardware Setup:** Configure HP Desktop (24 threads) for Turbo-compiling.
* [x] **ArduPilot SITL:** Build and run Copter simulation on Ubuntu 24.04.
* [x] **mlpack Setup:** Compile high-performance C++ ML library from source.
* [x] **Data Extraction:** Successfully convert `.BIN` logs to `.csv` using Python.

## Phase 2: Data Generation & Benchmarking (Current Phase)
* [ ] **Healthy Baseline:** Generate 10+ flight logs of "normal" flying.
* [ ] **Failure Simulation:** Modify SITL params to simulate battery sags and motor failure.
* [ ] **Feature Selection:** Identify which MAVLink messages (BAT, VIBE, IMU) are most predictive.
* [ ] **mlpack Benchmark:** Compare mlpack's KNN/RandomForest speed on the Desktop vs. Laptop.

## Phase 3: AI Integration & Proposal
* [ ] **Log Diagnosis Model:** Train a classifier to detect "Anomaly" vs "Normal."
* [ ] **C++ Implementation:** Use mlpack to run the diagnosis in real-time (C++).
* [ ] **GSoC Proposal Draft:** Combine logic, graphs (drone_health.png), and code samples.
* [ ] **Sync System:** Finalize Syncthing between Laptop and Desktop for field testing.
