# GSoC 2025 PROPOSAL — ArduPilot
## AI-Assisted Log Diagnosis & Root-Cause Detection
**[YOUR FULL REAL NAME]**

---

### 1. PERSONAL INFORMATION

- **Name:**           [Your full legal name]
- **Email:**          [Your email]
- **GitHub:**         https://github.com/BeastAyyG
- **University:**     [Full university name]
- **Degree:**         [e.g., B.Tech Computer Science]
- **Year:**           [e.g., 2nd year, expected graduation 2027]
- **Country:**        India
- **Timezone:**       IST (UTC+5:30)
- **Phone:**          [Your phone number]

---

### 2. PROJECT INFORMATION

- **Project Title:**  AI-Assisted Log Diagnosis & Root-Cause Detection
- **Project Number:** 5
- **Size:**           350 hours (Large)
- **Mentor:**         Nathaniel Mailhot

---

### 3. SYNOPSIS

Every day on discuss.ardupilot.org, users post flight logs asking "what went wrong?" Diagnosing failures from `.BIN` logs requires expert knowledge of dozens of message types and their normal ranges. Many posts wait days for a community member to analyze them. Some never get answered.

The existing automated analysis tools have significant gaps. DroneKit-LA (the most documented static analyzer) runs 15 rule-based tests — including compass vector length, EKF variance checks, GPS fix quality, gyro drift, and battery failsafe detection — but uses fixed thresholds (e.g., `compass_vector_length delta_fail=35%`, EKF velocity variance fail=1.0) that cannot adapt to different vehicle configurations. Mission Planner's bundled LogAnalyzer hasn't been updated since September 2017. Neither tool can detect cascading multi-failure scenarios or provide confidence-weighted diagnoses.

This project builds an ML-powered diagnostic tool that:

1. Extracts 60+ features from `.BIN` flight logs covering vibration, compass, power, GPS, motors, attitude, EKF health, IMU noise, and frequency-domain vibration patterns.
2. Classifies failure modes using a hybrid rule-based + XGBoost multi-label classifier, detecting multiple simultaneous failures in a single flight.
3. Provides confidence scores, specific evidence (which sensor values triggered the detection), and actionable fix recommendations.
4. Matches new logs against a database of known failure patterns linked to resolved forum threads.

The tool helps beginners get instant diagnosis and helps experts catch subtle multi-failure cascades they might miss during manual analysis.

---

### 4. WORKING PROTOTYPE (ALREADY BUILT)

**Repository:** https://github.com/BeastAyyG/ardupilot-log-diagnosis

I have built and tested a working prototype with three core components:

#### 4a. Log Parser
Parses any ArduPilot `.BIN` log file using `pymavlink.mavutil.mavlink_connection()`. Indexes all message types, extracts metadata (duration, vehicle type, firmware version, message counts), and returns structured Python dictionaries for downstream processing.

#### 4b. Feature Extractor (37 features from 6 message types)
Extracts numerical features from:

- **VIBE messages:** `vibe_x/y/z_mean`, `vibe_x/y/z_max`, `vibe_z_std`, `vibe_clip_total`
  *Context:* ArduPilot guidance states vibration below 30 m/s² is acceptable; above 60 m/s² causes altitude/position hold problems. Clip0/1/2 increasing indicates accelerometer saturation.

- **MAG messages:** `mag_field_mean`, `mag_field_max`, `mag_field_range`, `mag_field_std`, `mag_x_range`, `mag_y_range`
  *Context:* Compass/motor calibration doc states <30% interference acceptable, >60% requires relocation.

- **BAT messages:** `bat_volt_min`, `bat_volt_max`, `bat_volt_range`, `bat_volt_std`, `bat_curr_mean`, `bat_curr_max`, `bat_curr_std`
  *Context:* Battery failsafe triggers if voltage stays below BATT_LOW_VOLT for >10s.

- **GPS messages:** `gps_hdop_mean`, `gps_hdop_max`, `gps_nsats_mean`, `gps_nsats_min`, `gps_fix_pct`
  *Context:* DroneKit-LA uses satellites_min=5, hdop_min=5.0 as thresholds.

- **RCOU messages:** `motor_spread_mean`, `motor_spread_max`, `motor_spread_std`, `motor_ch1_mean`, `motor_output_std`, `motor_max_output`

- **ATT messages:** `att_roll_std`, `att_pitch_std`, `att_roll_max`, `att_pitch_max`, `att_desroll_err`

Output: single flat JSON dictionary mapping feature names to numerical values.

#### 4c. Diagnosis Engine (5 failure modes with confidence)
Rule-based detection for:

- **VIBRATION_HIGH** — triggers when `vibe_x/y/z_max > 30` or `clip_total > 0`. Confidence scales with severity (>60 adds 0.3, clipping adds 0.3).
- **COMPASS_INTERFERENCE** — triggers when `mag_field_range > 200` or `mag_field_std > 50`.
- **POWER_INSTABILITY** — triggers on voltage range, current spikes, and voltage sag patterns.
- **GPS_QUALITY_POOR** — triggers when `hdop_mean > 2.0` or `nsats_min < 6`.
- **MOTOR_IMBALANCE** — triggers when motor output spread exceeds 200 PWM between channels.

Each diagnosis includes:
- Confidence score (0–100%)
- Evidence list (exact features that triggered)
- Recommended fix action

Tested on:
- SITL-generated healthy flight logs
- SITL-simulated failure scenarios
- Real crash logs from discuss.ardupilot.org

**[INSERT SCREENSHOT OF TERMINAL OUTPUT HERE]**
*(You can generate this by running your CLI tool on a test log)*

#### 4d. Trained ML Model
Additionally trained an XGBoost classifier on SITL-generated failure data and an Isolation Forest for anomaly detection. These serve as proof-of-concept for the ML pipeline I will build during GSoC with a much larger labeled dataset.

---

### 5. TECHNICAL APPROACH

#### 5a. Feature Expansion (37 → 60+ features)

**New EKF features (from NKF4/XKF4 messages):**
- `ekf_vel_var_mean/max` — velocity variance (SV field)
- `ekf_pos_var_mean/max` — horizontal position variance (SP field)
- `ekf_hgt_var_mean/max` — height variance (SH field)
- `ekf_compass_var_mean/max` — compass variance (SM field)
- `ekf_flags_error_pct` — % of samples with bad SS (solution status) flags
- `ekf_innovation_max` — peak innovation from NKF3/XKF3

*Interpretation:* EKF2 documentation states values <0.3 are typical with good sensors; >1.0 means the EKF is rejecting that measurement source. EKF failsafe fires when any two of compass/position/velocity variances exceed FS_EKF_THRESH for 1 second.

**New IMU features (from IMU/ACC/GYR messages):**
- `imu_acc_x/y/z_std` — accelerometer noise per axis
- `imu_gyr_x/y/z_std` — gyroscope noise per axis
*(These detect sensor degradation and IMU inconsistency between redundant IMUs)*

**New FFT features:**
If `FFT_ENABLE=1` was set during flight, extract from FTN1 messages: PkAvg (peak average frequency), BwAvg (bandwidth average), SnX/Y/Z (signal-to-noise per axis).
If FTN1 data is unavailable, compute FFT from raw IMU AccX/AccY/AccZ data using `scipy.fft`:
- `fft_dominant_freq_x/y/z` — primary resonance frequency
- `fft_peak_power_x/y/z` — resonance strength
- `fft_noise_floor` — broadband noise level
*(This detects propeller blade-passage frequency spikes, motor bearing noise, and frame resonance)*

**New flight-phase features:**
Segment flight into takeoff/hover/cruise/descent/land phases. Extract per-phase statistics to isolate phase-specific anomalies (e.g., vibration only during descent = different root cause than constant vibration).

#### 5b. Multi-Label ML Classification

**Problem type:** Multi-label classification.
A single flight can exhibit MULTIPLE simultaneous failures. Real crashes often involve cascading failures:
`motor failure → vibration spike → EKF variance → crash`
`power brownout → GPS loss → flyaway`

This is why multi-class (exactly one label) is wrong for this domain. Multi-label lets us flag all contributing factors.

**Approach:** XGBoost 1.6+ supports multi-label classification natively using binary relevance — training (n_classes) binary classifiers with label matrix shaped (n_samples, n_classes) of 0/1 labels.

**Evaluation:** Per-label F1 score with macro averaging. sklearn's multi-label subset accuracy (exact match of entire label set) is too harsh for this problem. Per-label F1 gives credit for each correctly identified failure.

**Target:** >85% per-label F1 on held-out test set.

**Hybrid confidence merging:**
The final system runs BOTH rule-based detection AND ML inference, then merges results:
- Both agree    → High confidence (`0.7×ML_prob + 0.3×rule_conf + 0.05`)
- ML only       → Medium confidence (`ML_prob × 0.8`)
- Rules only    → Medium confidence (`rule_conf × 0.8`)

#### 5c. Retrieval System
Build a database of known failure patterns extracted from labeled forum crash reports. Each entry stores feature vector (60 values), failure type, root cause, forum thread URL, and the fix that resolved the issue. For new logs, compute cosine similarity between the extracted feature vector and all database entries. Report top-3 matches.

#### 5d. Output Format
Terminal output example:
```text
╔════════════════════════════════════════╗
║   ArduPilot Log Diagnosis Report      ║
╠════════════════════════════════════════╣
║  Log:      flight.BIN                 ║
║  Duration: 5m 42s                     ║
║  Vehicle:  ArduCopter 4.5.1           ║
╚════════════════════════════════════════╝

CRITICAL — VIBRATION_HIGH (95%)
  vibe_z_max = 67.8 (limit: 30.0)
  vibe_clip_total = 145 (limit: 0)
  Detected by: rule engine + ML model
  Similar to: discuss.ardupilot.org/t/15234
  Fix: Balance/replace propellers.

WARNING — MOTOR_IMBALANCE (54%)
  motor_spread_max = 312 (limit: 200)
  Detected by: ML model only
  Fix: Check individual motor/ESC health.

HEALTHY — compass, power, GPS, EKF normal

Overall: NOT SAFE TO FLY
```

---

### 6. COMPARISON WITH EXISTING TOOLS

| Feature | DroneKit-LA (best existing) | MP LogAnalyzer (legacy) | THIS PROJECT (proposed) |
| --- | --- | --- | --- |
| **Detection** | Rule-based | Rule-based | Rule + ML hybrid |
| **Tests** | 15 analyzers | ~12 tests | 10-13 failure types |
| **Thresholds** | Fixed | Fixed | Configurable + ML-learned |
| **Multi-failure** | No | No | Yes (multi-label) |
| **Confidence scores** | Pass/Warn/Fail | Pass/Warn/Fail | 0-100% with evidence |
| **Feature extraction** | Not applicable | Not applicable | 60+ features with FFT |
| **Retrieval** | No | No | Yes (similar case matching) |
| **Last updated** | Active but limited | Sept 2017 | New (2025) |
| **EKF analysis** | Basic variance check | None | Full NKF4/XKF4 analysis |
| **FFT vibration** | No | No | Yes (FTN1 or computed) |

**Key gap I address:** DroneKit-LA's EKF check uses fixed thresholds that cannot account for vehicle-specific normal ranges. My ML model learns what "normal" looks like and adapts accordingly. Neither tool detects cascading failures.

---

### 7. DETAILED TIMELINE

**COMMUNITY BONDING (before coding starts):**
- [ ] Set up development environment with mentor
- [ ] Agree on failure type priorities
- [ ] Identify initial set of labeled logs from forum
- [ ] Review ArduPilot coding style / contribution guide
- [ ] Set up CI/testing infrastructure

**Week 1 (May 26 – Jun 1): EKF Feature Extraction**
- Parse NKF1-NKF5 (EKF2) and XKF1-XKF5 (EKF3)
- Extract SV/SP/SH/SM variance ratios from NKF4/XKF4, innovation values, solution status flags
- Implement EKF failsafe signature detection
*DELIVERABLE:* EKF extractor producing 10 features

**Week 2 (Jun 2 – Jun 8): IMU + Attitude Features**
- Extract raw IMU accelerometer/gyroscope noise stats
- Detect IMU inconsistency between redundant sensors
- Add attitude tracking error features & control output features
*DELIVERABLE:* IMU + enhanced attitude extractors producing 12 additional features

**Week 3 (Jun 9 – Jun 15): FFT + Flight Phase Features**
- Parse FTN1/FTN2 messages if available, implement `scipy.fft` fallback
- Extract dominant frequency, peak power, noise floor
- Implement flight phase segmentation
*DELIVERABLE:* Complete feature pipeline producing 60+ features

**Week 4 (Jun 16 – Jun 22): Dataset Collection**
- Download 50+ `.BIN` files from discuss.ardupilot.org crash report threads
- Build labeling tool and document provenance
*DELIVERABLE:* 50+ labeled real-world logs with provenance documentation

**Week 5 (Jun 23 – Jun 29): Synthetic Data + Dataset Build**
- Script SITL failure simulations (motor failure, vibration, GPS loss, wind, RC failsafe)
- Generate 50+ synthetic failure logs and run feature pipeline
*DELIVERABLE:* Complete labeled dataset (100+ logs)

**Week 6 (Jun 30 – Jul 6): ML Training V1**
- Train/test split, train Random Forest baseline (One-vs-Rest)
- Compute per-label F1 and feature importance
*DELIVERABLE:* Baseline model with accuracy metrics report

**Week 7 — MIDTERM (Jul 7 – Jul 13)**
- Train XGBoost multi-label classifier using XGBoost native support
- Compare vs Random Forest, hyperparameter tuning
*DELIVERABLE:* Working ML classifier that beats rule-based engine, CLI demo

**Week 8 (Jul 14 – Jul 20): Hybrid Engine + Optimization**
- Implement hybrid merging
- Test edge cases and add new ML-detectable failure types
*DELIVERABLE:* Hybrid engine producing merged diagnoses

**Week 9 (Jul 21 – Jul 27): Retrieval System**
- Build known_failures database from labeled dataset
- Implement cosine similarity search
*DELIVERABLE:* Cosine similarity system matching similar flights

**Week 10 (Jul 28 – Aug 3): CLI Integration**
- Full argparse CLI (analyze, features, batch, compare)
- Handle large and corrupted logs
*DELIVERABLE:* Polished CLI tool installable via pip

**Week 11 (Aug 4 – Aug 10): Testing + MAVProxy Module**
- Comprehensive pytest suite
- MAVProxy module (stretch goal)
*DELIVERABLE:* Test suite + optional MAVProxy module

**Week 12 (Aug 11 – Aug 17): Documentation + Submission**
- ArduPilot wiki page, feature dictionary, failure type reference
- Demo video
*DELIVERABLE:* Complete documentation + submission-ready

**Buffer (Aug 18 – Aug 25): Mentor Feedback + Polish**
- Address comments, final testing on mentor-provided logs

---

### 8. ARDUPILOT CODE I HAVE STUDIED
- **Tools/LogAnalyzer/LogAnalyzer.py:** Existing rule-based framework.
- **libraries/AP_Logger/LogStructure.h:** Defines all DataFlash log message formats.
- **Tools/autotest/common.py:** Automated testing infrastructure.
- **libraries/AP_NavEKF2/ and libraries/AP_NavEKF3/:** EKF implementation source.
- **ArduPilot SITL simulation parameters:** `SIM_ENGINE_FAIL`, `SIM_ACC_RND`, `SIM_VIB_MOT_MAX`, etc.

---

### 9. MY CONTRIBUTIONS TO ARDUPILOT
1. **Documentation PR:** [LINK TO YOUR WIKI PR] 
   (Added Zorin OS mono-complete troubleshooting to the SITL setup documentation.)
2. **Discussion Forum:** [LINK TO YOUR DISCUSS THREAD]
   (Pre-application thread for Project 5 with prototype demonstration.)
3. **Discord:** Active in `#gsoc` channel with prototype updates.
4. **Prototype Repository:** https://github.com/BeastAyyG/ardupilot-log-diagnosis

---

### 10. RELEVANT EXPERIENCE
- **Coursework:** [List your programming courses — data structures, algorithms, etc.]
- **ML/Data Science:** [List any ML/data science coursework or self-study]
- **Projects:** 
  - Built a drone health monitoring system using `pymavlink` and `scikit-learn` that connects to ArduPilot SITL.
  - Successfully built and ran ArduPilot SITL from source on Linux.
  - [List any hackathons, competitions, or other projects]
- **Proficient in:** Python, NumPy, scikit-learn, pymavlink, Git, Linux command line.
- **Familiar with:** XGBoost, SciPy (FFT), pytest, argparse.

---

### 11. WHY THIS PROJECT
I chose this project after reading dozens of "please analyze my log" threads on the ArduPilot forum. In many of these threads, users waited days for help. In some, no expert ever responded.

An automated ML-powered diagnosis tool would give instant feedback to every user, catch multi-failure cascades that manual analysis often misses, and reduce the burden on experienced community members. The existing LogAnalyzer tools use fixed thresholds that cannot adapt. ML can learn the difference between "slightly elevated but normal for this vehicle" and "genuinely dangerous" from data.

---

### 12. AVAILABILITY
- **Hours per week:** 25-30 hours
- **Summer break:** [Your dates — "Available full-time from [date] to [date]"]
- **Exam periods:** [List any exam dates that overlap with GSoC — be honest]
- **Other commitments:** [Any part-time work, other courses, etc. — be honest]
- **Communication:** Available daily on Discord and email. Will provide weekly progress reports to mentor.
