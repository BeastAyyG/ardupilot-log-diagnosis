# Telemetry Feature Documentation

This document explains telemetry feature extraction fields used by the ArduPilot AI Log Diagnosis pipeline.

## GPS Features

| Feature | Source | Meaning | Units / Notes |
|----------|---------|----------|----------------|
| gps_hdop_mean | GPS | Average GPS Horizontal Dilution of Precision | Lower values are better |
| gps_hdop_max | GPS | Maximum GPS Horizontal Dilution of Precision observed | HDOP |
| gps_nsats_mean | GPS | Average number of connected satellites | Count |
| gps_nsats_min | GPS | Minimum satellites available during flight | Count |
| gps_fix_pct | GPS | Ratio of flight with GPS fix available | Ratio (0.0–1.0) |
| gps_hdop_tanomaly | GPS | Timestamp/metric for abnormal HDOP spikes | Anomaly metric |

## Vibration Features

| Feature | Source | Meaning | Units / Notes |
|----------|---------|----------|----------------|
| vibe_x_mean | VIBE | Average vibration on X-axis | m/s² |
| vibe_y_mean | VIBE | Average vibration on Y-axis | m/s² |
| vibe_z_mean | VIBE | Average vibration on Z-axis | m/s² |
| vibe_x_max | VIBE | Maximum X-axis vibration | m/s² |
| vibe_y_max | VIBE | Maximum Y-axis vibration | m/s² |
| vibe_z_max | VIBE | Maximum Z-axis vibration | m/s² |
| vibe_z_std | VIBE | Standard deviation of Z-axis vibration | m/s² |
| vibe_clip_total | VIBE | Total vibration clipping events | Count |
| vibe_z_tanomaly | VIBE | Timestamp/metric for abnormal vibration spikes | Anomaly metric |

## Power Features

| Feature | Source | Meaning | Units / Notes |
|----------|---------|----------|----------------|
| bat_volt_min | BAT/CURR | Minimum battery voltage | Volts |
| bat_volt_max | BAT/CURR | Maximum battery voltage | Volts |
| bat_volt_range | BAT/CURR | Difference between min and max voltage | Volts |
| bat_volt_std | BAT/CURR | Variation in battery voltage | Standard deviation |
| bat_curr_mean | BAT/CURR | Average battery current | Amps |
| bat_curr_max | BAT/CURR | Maximum battery current | Amps |
| bat_curr_std | BAT/CURR | Variation in battery current | Standard deviation |
| bat_margin | BAT/CURR | Battery safety margin | Health indicator |
| bat_sag_ratio | BAT/CURR | Voltage drop under load | Ratio |
| volt_tanomaly | BAT/CURR | Detects abnormal voltage behavior | Anomaly metric |

## Motor Features

| Feature | Source | Meaning | Units / Notes |
|----------|---------|----------|----------------|
| motor_spread_mean | RCOU | Average difference between motor outputs | Distribution metric |
| motor_spread_max | RCOU | Maximum difference between motor outputs | Distribution metric |
| motor_spread_std | RCOU | Variation in motor output spread | Standard deviation |
| motor_output_mean | RCOU | Average motor output | Percentage |
| motor_output_std | RCOU | Variation in motor output | Standard deviation |
| motor_max_output | RCOU | Maximum motor output | Percentage |
| motor_hover_ratio | RCOU | Motor output during hover | Ratio |
| motor_spread_tanomaly | RCOU | Detects abnormal motor spread | Anomaly metric |
| motor_saturation_pct | RCOU | Percentage of time motors reached saturation | Percentage |
| motor_all_high_pct | RCOU | Percentage of time all motors ran high | Percentage |

## IMU Features

| Feature | Source | Meaning | Units / Notes |
|----------|---------|----------|----------------|
| imu_acc_x_std | IMU | X-axis acceleration variation | Standard deviation |
| imu_acc_y_std | IMU | Y-axis acceleration variation | Standard deviation |
| imu_acc_z_std | IMU | Z-axis acceleration variation | Standard deviation |
| imu_gyr_x_std | IMU | X-axis gyroscope variation | Standard deviation |
| imu_gyr_y_std | IMU | Y-axis gyroscope variation | Standard deviation |
| imu_gyr_z_std | IMU | Z-axis gyroscope variation | Standard deviation |

## FFT Features

| Feature | Source | Meaning | Units / Notes |
|----------|---------|----------|----------------|
| fft_dominant_freq_x | FTN1 | Dominant X-axis frequency | Hz |
| fft_dominant_freq_y | FTN1 | Dominant Y-axis frequency | Hz |
| fft_dominant_freq_z | FTN1 | Dominant Z-axis frequency | Hz |
| fft_peak_power_x | FTN1 | Peak spectral power on X-axis | Spectrum metric |
| fft_peak_power_y | FTN1 | Peak spectral power on Y-axis | Spectrum metric |
| fft_peak_power_z | FTN1 | Peak spectral power on Z-axis | Spectrum metric |
| fft_noise_floor | FTN1 | Background signal noise level | Noise metric |

## Event Features

| Feature | Source | Meaning | Units / Notes |
|----------|---------|----------|----------------|
| evt_error_count | ERR | Total detected errors | Count |
| evt_failsafe_count | ERR | Number of failsafe events | Count |
| evt_mode_change_count | MODE | Flight mode switches | Count |
| evt_unexpected_mode_changes | MODE | Unexpected mode transitions | Count |
| evt_crash_detected | ERR | Crash detection indicator | Boolean |
| evt_gps_lost_count | ERR | Number of GPS loss events | Count |
| evt_rc_lost_count | ERR | Number of RC signal loss events | Count |
| evt_radio_failsafe_count | ERR | Number of radio failsafe events | Count |

## EKF Features

| Feature | Source | Meaning | Units / Notes |
|----------|---------|----------|----------------|
| ekf_vel_var_mean | XKF4/NKF4 | Average velocity variance | Stability indicator |
| ekf_vel_var_max | XKF4/NKF4 | Maximum velocity variance | Stability indicator |
| ekf_pos_var_mean | XKF4/NKF4 | Average position variance | Stability indicator |
| ekf_pos_var_max | XKF4/NKF4 | Maximum position variance | Stability indicator |
| ekf_hgt_var_mean | XKF4/NKF4 | Average height variance | Stability indicator |
| ekf_hgt_var_max | XKF4/NKF4 | Maximum height variance | Stability indicator |
| ekf_compass_var_mean | XKF4/NKF4 | Average compass variance | Stability indicator |
| ekf_compass_var_max | XKF4/NKF4 | Maximum compass variance | Stability indicator |
| ekf_flags_error_pct | XKF4/NKF4 | Percentage of EKF error flags | Percentage |
| ekf_lane_switch_count | XKF4/NKF4 | Number of EKF lane changes | Count |
| ekf_pos_var_tanomaly | XKF4/NKF4 | Detects abnormal position variance | Anomaly metric |

## System Features

| Feature | Source | Meaning | Units / Notes |
|----------|---------|----------|----------------|
| sys_long_loops | PM | Number of long processing loops | Count |
| sys_max_loop_time | PM | Maximum loop execution time | Milliseconds |
| sys_cpu_load_mean | PM | Average CPU load | Percentage |
| sys_internal_errors | PM | Internal system error count | Count |
| sys_vcc_min | PM | Minimum board voltage | Volts |
| sys_vcc_range | PM | Variation in board voltage | Volts |
| sys_vservo_min | PM | Minimum servo voltage | Volts |

## Control Features

| Feature | Source | Meaning | Units / Notes |
|----------|---------|----------|----------------|
| ctrl_thr_out_mean | CTUN | Average throttle output | Percentage |
| ctrl_thr_hover_ratio | CTUN | Throttle level while hovering | Ratio |
| ctrl_alt_error_max | CTUN | Maximum altitude error | Meters |
| ctrl_alt_error_std | CTUN | Variation in altitude error | Standard deviation |
| ctrl_climb_rate_std | CTUN | Variation in climb rate | Standard deviation |
| ctrl_thr_saturated_pct | CTUN | Percentage of throttle saturation | Percentage |

## Compass Features

| Feature | Source | Meaning | Units / Notes |
|----------|---------|----------|----------------|
| mag_field_mean | MAG | Average magnetic field strength | Sensor metric |
| mag_field_max | MAG | Maximum magnetic field strength | Sensor metric |
| mag_field_range | MAG | Range of magnetic field values | Sensor metric |
| mag_field_std | MAG | Magnetic field variation | Standard deviation |
| mag_x_range | MAG | Range of X-axis magnetic field | Sensor metric |
| mag_y_range | MAG | Range of Y-axis magnetic field | Sensor metric |
| mag_tanomaly | MAG | Detects abnormal magnetic field behavior | Anomaly metric |

## Attitude Features

| Feature | Source | Meaning | Units / Notes |
|----------|---------|----------|----------------|
| att_roll_std | ATT | Roll variation | Degrees |
| att_pitch_std | ATT | Pitch variation | Degrees |
| att_roll_max | ATT | Maximum roll angle | Degrees |
| att_pitch_max | ATT | Maximum pitch angle | Degrees |
| att_desroll_err | ATT | Difference between desired and actual roll | Error metric |
| att_early_divergence | ATT | Early flight instability indicator | Stability metric |
| att_time_to_crash_sec | ATT | Estimated time before crash | Seconds |

## Derived Features

| Feature | Source | Meaning | Units / Notes |
|----------|---------|----------|----------------|
| thrust_weight_ratio | Derived | Ratio of thrust to vehicle weight | Ratio |
| voltage_internal_resistance | Derived | Estimated internal battery resistance | Derived metric |
| attitude_tracking_error | Derived | Difference between commanded and actual attitude | Error metric |
| ekf_health_composite | Derived | Combined EKF health score | Composite metric |
| motor_symmetry_index | Derived | Balance across motors | Stability indicator |
| vibe_to_clip_ratio | Derived | Relationship between vibration and clipping | Ratio |
| gps_reliability_score | Derived | Overall GPS quality score | Composite metric |