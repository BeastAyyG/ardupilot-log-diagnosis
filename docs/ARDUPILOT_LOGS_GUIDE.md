# ArduPilot Log Sources for Diagnostic Tool Testing

## Executive Summary

This guide provides the most efficient methods to find ArduPilot `.BIN` logs that match your tool's requirements for GSoC demonstration. The logs are categorized by failure type and source reliability.

---

## 1. PRIMARY SOURCES (Highest Quality)

### 1.1 ArduPilot Discuss Forum (Copter Section) ⭐⭐⭐
**URL:** https://discuss.ardupilot.org/c/arducopter

**How to Search Efficiently:**
- Navigate to **Copter > Copter 4.x** categories
- Search for keywords in thread titles:
  - `"sudden flip"`
  - `"crash"`
  - `"EKF variance"`
  - `"flyaway"`
  - `"unexplained"`
  - `"vibration"`
  - `"compass"`
  - `"motor imbalance"`

**What to Look For:**
- Threads with `.BIN` file attachments or Google Drive/Dropbox links
- Posts where users describe cascading failures
- Maintainer responses that confirm root cause

**Example Found Log (PERFECT for your tool):**
- **Thread:** "Vibration, EKF variance and associated GPS Glitch results in cascading failsafe"
- **URL:** https://discuss.ardupilot.org/t/vibration-ekf-variance-and-associated-gps-glitch-results-in-cascading-failsafe/62244
- **Log Download:** https://drive.google.com/file/d/1saTjRkaS0cboV-Zhy1M_ri2aMCVCc1QN/view?usp=sharing
- **Scenario:** Vibration → EKF variance → GPS Glitch → Crash (EXACT cascading failure you need!)
- **Vehicle:** 210g quadcopter, 4-inch props, Omnibus nano F4 V6
- **Firmware:** Copter 4.0.3

---

### 1.2 GitHub ArduPilot Issues ⭐⭐⭐
**URL:** https://github.com/ArduPilot/ardupilot/issues

**Search Queries:**
```
is:issue label:bug copter crash log
is:issue "EKF variance" .bin
is:issue "vibration" crash log
is:issue motor imbalance
```

**Notable Issues with Logs:**
- **Issue #15489:** "Vibration induced EKF variance results in unnecessary GPS failsafe"
  - **Logs:** Two cascading failure logs available
  - **Download:** https://drive.google.com/file/d/1saTjRkaS0cboV-Zhy1M_ri2aMCVCc1QN/view?usp=sharing
  - **Second Log:** https://drive.google.com/file/d/1c5jXscqNnUXMsJ1t7VjjAYslU6AVxV57/view?usp=sharing
  - **Perfect for:** Testing Temporal Causal Arbiter

- **Issue #5859:** "RC Inputs & Outputs freeze randomly (crashlog)"
  - **Scenario:** Motor/ESC failure in hexacopter
  - **Good for:** Motor spread analysis

---

## 2. PUBLIC DATASETS (Ready to Download)

### 2.1 BASiC Dataset (Biomisa ArduCopter Sensory Critique) ⭐⭐⭐
**URL:** https://doi.org/10.5281/zenodo.8195068

**Description:**
- 70+ autonomous flights with injected sensor failures
- 7+ hours of flight data
- Includes: GPS, RC, Accelerometer, Gyroscope, Compass, Barometer failures
- Formats: `.bin`, `.log`, `.mat`, `.csv` (processed)

**Failure Types Available:**
| Sensor | Pre-Failure | Post-Failure |
|--------|-------------|--------------|
| GPS Status | 6 | 1 |
| Compass Health | 1 | 0 |
| IMU (Accel/Gyro) | 1 | 0 |
| Barometer Health | 1 | 0 |

**Best For:**
- Training your ML model on known failure patterns
- Validating rule engine detection accuracy

---

### 2.2 UAV-SEAD Dataset ⭐⭐
**URL:** https://arxiv.org/abs/2502.13900

**Description:**
- 1,404 real flights (53+ hours)
- 900 normal flights, 504 with anomalies
- PX4-based but similar logging structure
- Annotated anomaly timestamps

**Anomaly Categories:**
- Mechanical/Electrical (47 flights)
- External Position (197 flights)
- Global Position (41 flights)
- Altitude (78 flights)

**Best For:**
- Testing false positive rates
- Cross-validation with PX4 logs

---

### 2.3 RflyMAD Dataset ⭐⭐⭐
**Description:**
- 114 GB of data
- 5,629 flight cases
- 11 fault types across 6 flight statuses
- 3,283 minutes of fault time

**Composition:**
- 2,566 SIL simulation cases
- 2,566 HIL simulation cases
- 497 real flight cases

**Fault Types:**
- Actuators (motors, propellers)
- Sensors (accel, gyro, mag, baro, GPS)
- Environmental effects

**Best For:**
- Large-scale ML training
- Comprehensive fault coverage

---

### 2.4 UAV-Realistic-Fault-Dataset (GitHub) ⭐⭐
**URL:** https://github.com/tiiuae/UAV-Realistic-Fault-Dataset

**Description:**
- Indoor missions with propeller damage
- 5 classes: 0-Normal, 1-4 Broken Propellers
- Accelerometer, Gyroscope, Audio data

**Best For:**
- Motor imbalance detection
- Physical damage analysis

---

### 2.5 UAV-FD Dataset ⭐⭐
**Description:**
- Hexarotor DJI frame with Pixhawk/ArduPilot
- 18 manual outdoor flights
- 12 faulty flights with chipped blades

**Best For:**
- Motor/propeller failure analysis
- Hexacopter motor spread testing

---

## 3. SPECIFIC LOG TYPES & WHERE TO FIND THEM

### 3.1 Cascading Failures (Vibration → Compass → EKF → Crash)
**Best Sources:**
1. ArduPilot Discuss Forum - Search "cascading failsafe"
2. GitHub Issue #15489 (linked above)
3. Thread: https://discuss.ardupilot.org/t/vibration-ekf-variance-and-associated-gps-glitch-results-in-cascading-failsafe/62244

**Log Messages to Verify:**
- `VIBE` message shows increasing vibration
- `MAG` message shows magnetic field fluctuations
- `XKF4` message shows EKF variance > 1.0
- `ERR` message with Subsys=16 (EKF Check)

---

### 3.2 Motor Imbalance (Bent Propeller/Unbalanced Weight)
**Best Sources:**
1. UAV-Realistic-Fault-Dataset (GitHub)
2. BASiC Dataset (motor failure scenarios)
3. ArduPilot Discuss - Search "motor imbalance" or "hot motor"

**Log Messages to Verify:**
- `RCOU` message shows one motor working 20-30% harder
- `MOTB` message (motor mixer info)
- `ESC` telemetry (if available) shows RPM differences

**Analysis Tip:**
Look for `motor_spread_mean` > 15% between highest and lowest motor output during hover.

---

### 3.3 Brownouts/Power Instability
**Best Sources:**
1. ArduPilot Discuss - Search "brownout" or "voltage sag"
2. BASiC Dataset

**Log Messages to Verify:**
- `BAT` message shows voltage sag under throttle
- `POWR` message shows VCC fluctuations > 0.15V
- `DSF` message (logging statistics) may show gaps

---

### 3.4 Compass EMI (Interference from Power Wires)
**Best Sources:**
1. ArduPilot Discuss - Search "compass variance" or "mag interference"
2. BASiC Dataset (compass failures)

**Log Messages to Verify:**
- `MAG` message shows field strength fluctuating > 35% with throttle
- `COMPASS` message (raw MagX, MagY, MagZ values)
- Interference spikes correlate with `RCOU` throttle increases

---

## 4. EFFICIENT SEARCH WORKFLOW

### Step 1: Start with Public Datasets (30 minutes)
1. Download BASiC Dataset (zenodo) - 70 flights with known failures
2. Download UAV-Realistic-Fault-Dataset (GitHub) - propeller damage
3. These give you immediate, labeled data for testing

### Step 2: Mine ArduPilot Discuss Forum (1-2 hours)
1. Go to https://discuss.ardupilot.org/c/arducopter/copter-4-6/165
2. Use browser search (Ctrl+F) for keywords:
   - "crash"
   - "EKF"
   - "vibration"
   - "flyaway"
   - "bin"
3. Open threads with Google Drive/Dropbox links
4. Download `.BIN` files to organized folders:
   ```
   /logs/
     /cascading_failures/
     /motor_imbalance/
     /power_issues/
     /compass_emi/
   ```

### Step 3: GitHub Issues (30 minutes)
1. Search: `is:issue ardupilot copter crash log .bin`
2. Look for issues with Google Drive links
3. Download and categorize

### Step 4: Verify Log Completeness (Critical!)
Before running your tool, verify the log contains:
- ✅ `VIBE` messages (vibration data)
- ✅ `MAG` or `COMPASS` messages (compass data)
- ✅ `BAT` messages (battery data)
- ✅ `RCOU` messages (motor outputs)
- ✅ `XKF` or `NKF` messages (EKF data)

**If any are missing, your parser may fail!**

---

## 5. LOG VERIFICATION CHECKLIST

Before using a log for your demo, verify:

| Check | How to Verify | Tool |
|-------|---------------|------|
| Vehicle Type | Check `MSG` messages for firmware type | MAVExplorer |
| Copter (not Plane/Rover) | Verify `MODE` message shows copter modes | Mission Planner |
| Complete Telemetry | Check all required messages present | UAV LogViewer |
| Real Flight (not bench test) | `GPS` shows movement, `BARO` shows altitude change | MAVExplorer |
| Crash Occurred | `ERR` message with Subsys=12, or log ends abruptly | Mission Planner |

---

## 6. RECOMMENDED LOGS FOR GSoC DEMO

### Top 3 Logs to Download First:

1. **Cascading Failure Log**
   - **Source:** GitHub Issue #15489
   - **URL:** https://drive.google.com/file/d/1saTjRkaS0cboV-Zhy1M_ri2aMCVCc1QN/view?usp=sharing
   - **Why:** Perfect example of vibration → EKF → GPS glitch cascade
   - **Expected Tool Output:** "Vibration" as root cause (suppress EKF/GPS warnings)

2. **Motor Imbalance Log**
   - **Source:** UAV-Realistic-Fault-Dataset
   - **URL:** https://github.com/tiiuae/UAV-Realistic-Fault-Dataset
   - **Why:** Controlled propeller damage with known severity
   - **Expected Tool Output:** "Motor Imbalance" with specific motor identification

3. **Compass EMI Log**
   - **Source:** BASiC Dataset
   - **URL:** https://doi.org/10.5281/zenodo.8195068
   - **Why:** Injected compass failures with ground truth
   - **Expected Tool Output:** "Compass Interference" with correlation to throttle

---

## 7. TOOLS FOR LOG ANALYSIS

### Pre-Analysis (Before Running Your Tool):
1. **UAV LogViewer** (Web): https://ardupilot.org/planner/docs/common-uavlogviewer.html
   - Quick visualization of log contents
   - Verify messages present

2. **MAVExplorer** (Python):
   ```bash
   MAVExplorer.py flight.bin
   ```
   - Command-line analysis
   - Extract specific messages

3. **Mission Planner:**
   - Download logs from autopilot
   - Basic plotting and analysis

### Post-Analysis (Verify Your Tool's Output):
1. **ArduPilot WebTools:**
   - Filter Review: https://firmware.ardupilot.org/Tools/WebTools/FilterReview/
   - MAGFit: https://firmware.ardupilot.org/Tools/WebTools/MAGFit/
   - PID Review: https://firmware.ardupilot.org/Tools/WebTools/PIDReview/

---

## 8. AVOID THESE LOGS

| Type | Why to Avoid | How to Identify |
|------|--------------|-----------------|
| ArduPlane/Rover logs | Your tool is optimized for Copters | Check `MSG` for "ArduPlane" or "ArduRover" |
| Bench tests | No real flight dynamics | `GPS` stationary, `BARO` flat |
| Logs with missing telemetry | Parser will fail | Missing `VIBE`, `MAG`, `BAT`, or `RCOU` |
| Very short flights (< 30s) | Not enough data for analysis | Log duration in filename or `GPS` message |
| Firmware < 3.6 | Different message formats | Check `MSG` for version info |

---

## 9. QUICK REFERENCE: LOG MESSAGE CODES

### Error Subsystems (ERR message):
| Code | Subsystem | Your Tool Should Detect |
|------|-----------|------------------------|
| 3 | Compass | Compass failures/EMI |
| 5 | Radio Failsafe | Communication issues |
| 6 | Battery Failsafe | Power/brownout issues |
| 12 | Crash Check | Mechanical failures |
| 16 | EKF Check | Navigation filter issues |
| 17 | EKF Failsafe | Cascading EKF failures |
| 25 | Thrust Loss | Motor/propeller issues |
| 29 | Vibration Failsafe | High vibration issues |

### Key Log Messages for Your Tool:
| Message | Contains | Used For |
|---------|----------|----------|
| `VIBE` | Vibration levels (X, Y, Z) | Vibration analysis |
| `MAG` | Magnetometer readings | Compass health |
| `COMPASS` | Raw compass values | EMI detection |
| `BAT` | Battery voltage/current | Brownout detection |
| `RCOU` | Motor PWM outputs | Motor imbalance |
| `ESC` | ESC telemetry (RPM, temp) | Motor health |
| `XKF4` | EKF variances | Navigation health |
| `ERR` | Error events | Failure timeline |
| `MODE` | Flight mode changes | Context analysis |

---

## 10. SUMMARY: MOST EFFICIENT APPROACH

### For Immediate Testing (Today):
1. Download BASiC Dataset: https://doi.org/10.5281/zenodo.8195068
2. Download GitHub Issue #15489 log: https://drive.google.com/file/d/1saTjRkaS0cboV-Zhy1M_ri2aMCVCc1QN/view?usp=sharing
3. Download UAV-Realistic-Fault-Dataset: https://github.com/tiiuae/UAV-Realistic-Fault-Dataset

### For GSoC Demo (This Week):
1. Search ArduPilot Discuss for 5-10 crash threads with `.BIN` links
2. Download and verify each log has complete telemetry
3. Run your tool on each log
4. Compare your diagnosis with maintainer conclusions in threads
5. Document cases where your Temporal Causal Arbiter correctly identifies root cause

### For Training/Validation:
1. Use BASiC Dataset (labeled failures)
2. Use RflyMAD (large-scale simulation data)
3. Split into train/test sets for ML model validation

---

## APPENDIX: USEFUL URLS

| Resource | URL |
|----------|-----|
| ArduPilot Discuss (Copter) | https://discuss.ardupilot.org/c/arducopter |
| ArduPilot GitHub Issues | https://github.com/ArduPilot/ardupilot/issues |
| BASiC Dataset | https://doi.org/10.5281/zenodo.8195068 |
| UAV-Realistic-Fault-Dataset | https://github.com/tiiuae/UAV-Realistic-Fault-Dataset |
| UAV LogViewer | https://ardupilot.org/planner/docs/common-uavlogviewer.html |
| MAVExplorer | Included with MAVProxy |
| ArduPilot WebTools | https://firmware.ardupilot.org/Tools/WebTools/ |
| Log Messages Reference | https://ardupilot.org/copter/docs/logmessages.html |

---

*Document Version: 1.0*
*Last Updated: 2026-03-17*
