# Feature Dictionary

This document describes the 60+ features extracted from ArduPilot `.BIN` log messages and fed into the AI models or Rule Engines.

## VIBE Messages
**Extracted by:** `src/features/vibration.py`

| Feature Name | Description | Source Field | Unit / Value Range |
|--------------|-------------|--------------|---------------------|
| `vibe_x_mean` | Baseline X-axis vibration | `VibeX` | m/s/s |
| `vibe_y_mean` | Baseline Y-axis vibration | `VibeY` | m/s/s |
| `vibe_z_mean` | Baseline Z-axis vibration | `VibeZ` | m/s/s |
| `vibe_x_max`  | Peak X-axis vibration | `VibeX` | m/s/s |
| `vibe_y_max`  | Peak Y-axis vibration | `VibeY` | m/s/s |
| `vibe_z_max`  | Peak Z-axis vibration | `VibeZ` | m/s/s (Threshold > 30 is bad) |
| `vibe_clip_total` | Total clipping events | sum(`Clip0` + `Clip1` + `Clip2`) | Count (Ideal: 0) |
| `vibe_z_std`  | Standard deviation of Z vibration | `VibeZ` | Dispersion metric |

## MAG Messages
**Extracted by:** `src/features/compass.py`

| Feature Name | Description | Source Field | Unit / Value Range |
|--------------|-------------|--------------|---------------------|
| `mag_field_mean` | Baseline magnetic field strength | `sqrt(MagX^2+MagY^2+MagZ^2)` | mGauss |
| `mag_field_range` | Variation in compass fields | `max-min` | Range (High range = interference) |

## BAT Messages
**Extracted by:** `src/features/power.py`

| Feature Name | Description | Source Field | Unit / Value Range |
|--------------|-------------|--------------|---------------------|
| `bat_volt_min` | Lowest voltage detected | `Volt` | Volts (Check for sag/brownout) |
| `bat_curr_max` | Maximum current draw | `Curr` | Amps |

---

Additional implemented extractors:
- `src/features/gps.py`
- `src/features/motors.py`
- `src/features/attitude.py`
