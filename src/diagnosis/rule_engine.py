import yaml
from pathlib import Path
from src.constants import DEFAULT_THRESHOLDS
from .failure_types import FAILURE_RECOMMENDATIONS

class RuleEngine:
    """Threshold-based failure detection."""
    
    def __init__(self, thresholds: dict = None, config_path: str = None):
        if config_path and Path(config_path).exists():
            with open(config_path, 'r') as f:
                # Load from YAML and flatten for simplistic access
                loaded = yaml.safe_load(f)
                self.thresholds = {}
                for k, v in loaded.items():
                    if isinstance(v, dict):
                        for sub_k, sub_v in v.items():
                            self.thresholds[sub_k] = sub_v
                    else:
                        self.thresholds[k] = v
        else:
            self.thresholds = thresholds or DEFAULT_THRESHOLDS
            
    def diagnose(self, features: dict) -> list:
        results = []
        for check in [
            self._check_vibration,
            self._check_compass,
            self._check_power,
            self._check_gps,
            self._check_motors,
            self._check_ekf,
            self._check_system,
            self._check_rc_failsafe,
            self._check_events
        ]:
            result = check(features)
            if result and result["confidence"] > 0:
                results.append(result)
                
        results.sort(key=lambda x: x["confidence"], reverse=True)
        return results

    def _check_vibration(self, features):
        vibe_x = features.get("vibe_x_max", 0.0)
        vibe_y = features.get("vibe_y_max", 0.0)
        vibe_z = features.get("vibe_z_max", 0.0)
        clip = features.get("vibe_clip_total", 0.0)
        
        warn = self.thresholds.get("vibe_max_warn", 30.0)
        fail = self.thresholds.get("vibe_max_fail", 60.0)
        
        triggered = (vibe_x > warn or vibe_y > warn or vibe_z > warn or clip > 0)
        if not triggered: return None
        
        base = 0.0
        evidence = []
        for axis, val in [("x", vibe_x), ("y", vibe_y), ("z", vibe_z)]:
            if val > fail:
                base += 0.2
                evidence.append({"feature": f"vibe_{axis}_max", "value": val, "threshold": fail, "direction": "above"})
            elif val > warn:
                base += 0.1
                evidence.append({"feature": f"vibe_{axis}_max", "value": val, "threshold": warn, "direction": "above"})
                
        if clip > 0:
            base += 0.3
            evidence.append({"feature": "vibe_clip_total", "value": clip, "threshold": 0, "direction": "above"})
        if clip > 100:
            base += 0.2
            
        conf = min(base, 1.0)
        severity = "critical" if conf > 0.7 else ("warning" if conf > 0.3 else "info")
        
        return {
            "failure_type": "vibration_high", "confidence": conf, "severity": severity,
            "detection_method": "rule", "evidence": evidence,
            "recommendation": FAILURE_RECOMMENDATIONS["vibration_high"]
        }

    def _check_compass(self, features):
        mag_rng = features.get("mag_field_range", 0.0)
        mag_std = features.get("mag_field_std", 0.0)
        
        rng_lim = self.thresholds.get("mag_range_limit", 200.0)
        std_lim = self.thresholds.get("mag_std_limit", 50.0)
        
        if mag_rng <= rng_lim and mag_std <= std_lim:
            return None
            
        conf = 0.0
        evidence = []
        if mag_rng > 400:
            conf = 0.9
            evidence.append({"feature": "mag_field_range", "value": mag_rng, "threshold": 400, "direction": "above"})
        elif mag_rng > rng_lim:
            conf = 0.5
            evidence.append({"feature": "mag_field_range", "value": mag_rng, "threshold": rng_lim, "direction": "above"})
            
        if mag_std > 100:
            conf = min(conf + 0.3, 1.0)
            evidence.append({"feature": "mag_field_std", "value": mag_std, "threshold": 100, "direction": "above"})
        elif mag_std > std_lim:
            conf = min(conf + 0.15, 1.0)
            evidence.append({"feature": "mag_field_std", "value": mag_std, "threshold": std_lim, "direction": "above"})
            
        conf = max(conf, 0.1) # Minimum if triggered
        severity = "critical" if conf > 0.6 else "warning"
        return {
            "failure_type": "compass_interference", "confidence": conf, "severity": severity,
            "detection_method": "rule", "evidence": evidence,
            "recommendation": FAILURE_RECOMMENDATIONS["compass_interference"]
        }

    def _check_power(self, features):
        volt_rng = features.get("bat_volt_range", 0.0)
        volt_min = features.get("bat_volt_min", 20.0) # assume safe unless proven otherwise
        vcc_min = features.get("sys_vcc_min", 5.0)
        margin = features.get("bat_margin", 10.0)
        
        lim_rng = self.thresholds.get("bat_volt_range_limit", 2.0)
        lim_vcc = self.thresholds.get("powr_vcc_min", 4.5)
        
        evidence = []
        conf = 0.0
        failure = None
        severity = "warning"
        msg = ""
        
        if volt_rng > lim_rng:
            conf += 0.5
            evidence.append({"feature": "bat_volt_range", "value": volt_rng, "threshold": lim_rng, "direction": "above"})
            failure = "power_instability"
            msg = "Battery may be failing or underpowered for vehicle weight"
            
        if vcc_min > 0 and vcc_min < lim_vcc:
            conf += 0.8
            evidence.append({"feature": "sys_vcc_min", "value": vcc_min, "threshold": lim_vcc, "direction": "below"})
            failure = "brownout"
            severity = "critical"
            msg = "Board voltage low — check power supply, possible brownout risk"
            
        if margin < 0.5 and margin > 0: # Only if positive and very close to failsafe
            conf += 0.4
            evidence.append({"feature": "bat_margin", "value": margin, "threshold": 0.5, "direction": "below"})
            if not failure: 
                failure = "power_instability"
                msg = "Battery voltage approaching failsafe threshold"
            
        if volt_min > 0 and volt_min < self.thresholds.get("volt_min_absolute", 10.0):
            conf += 0.3
            evidence.append({"feature": "bat_volt_min", "value": volt_min, "threshold": self.thresholds.get("volt_min_absolute", 10.0), "direction": "below"})
            if not failure: failure = "power_instability"
            
        if not evidence: return None
        conf = min(conf, 1.0)
        return {
            "failure_type": failure, "confidence": conf, "severity": severity,
            "detection_method": "rule", "evidence": evidence,
            "recommendation": msg or FAILURE_RECOMMENDATIONS["power_instability"]
        }

    def _check_gps(self, features):
        hdop = features.get("gps_hdop_mean", 0.0)
        nsats = features.get("gps_nsats_min", 10.0)
        fix_pct = features.get("gps_fix_pct", 1.0)
        lost = features.get("evt_gps_lost_count", 0.0)
        
        lim_hdop = self.thresholds.get("gps_hdop_limit", 2.0)
        lim_nsats = self.thresholds.get("gps_nsats_min", 6)
        
        evidence = []
        conf = 0.0
        if hdop > lim_hdop:
            conf += 0.4
            evidence.append({"feature": "gps_hdop_mean", "value": hdop, "threshold": lim_hdop, "direction": "above"})
        if nsats > 0 and nsats < lim_nsats:
            conf += 0.5
            evidence.append({"feature": "gps_nsats_min", "value": nsats, "threshold": lim_nsats, "direction": "below"})
        if fix_pct < 0.95:
            conf += 0.6
            evidence.append({"feature": "gps_fix_pct", "value": fix_pct, "threshold": 0.95, "direction": "below"})
        if lost > 0:
            conf += 0.8
            evidence.append({"feature": "evt_gps_lost_count", "value": lost, "threshold": 0, "direction": "above"})
            
        if not evidence: return None
        conf = min(conf, 1.0)
        severity = "critical" if conf > 0.7 else "warning"
        
        return {
            "failure_type": "gps_quality_poor", "confidence": conf, "severity": severity,
            "detection_method": "rule", "evidence": evidence,
            "recommendation": FAILURE_RECOMMENDATIONS["gps_quality_poor"]
        }

    def _check_motors(self, features):
        spread_max = features.get("motor_spread_max", 0.0)
        spread_mean = features.get("motor_spread_mean", 0.0)
        spread_std = features.get("motor_spread_std", 0.0)
        roll_std = features.get("att_roll_std", 0.0)
        
        # Raised significantly: old 200/100 fired on >90% of all flights.
        # A healthy quad at hover routinely has spread of 100-250 PWM.
        # True motor imbalance shows sustained high spread.
        lim_spr = self.thresholds.get("motor_spread_limit", 400.0)   # was 200
        lim_mean = self.thresholds.get("spread_mean_limit", 200.0)   # was 100
        
        if spread_max <= lim_spr and spread_mean <= lim_mean:
            return None
            
        evidence = []
        conf = 0.0
        failure = "motor_imbalance"

        # Require both max AND mean to be elevated for high confidence
        # This avoids calling a single-spike transient a motor failure
        both_elevated = spread_max > lim_spr and spread_mean > lim_mean
        
        if spread_max >= (lim_spr * 1.5):  # 600+ PWM = very severe
            conf += 0.55
            evidence.append({"feature": "motor_spread_max", "value": spread_max, "threshold": lim_spr * 1.5, "direction": "above"})
        elif spread_max > lim_spr:
            conf += 0.30 if both_elevated else 0.15  # lower if mean is ok
            evidence.append({"feature": "motor_spread_max", "value": spread_max, "threshold": lim_spr, "direction": "above"})

        if spread_mean >= (lim_mean * 1.5):  # 300+ sustained mean = definite imbalance
            conf += 0.40
            evidence.append({"feature": "motor_spread_mean", "value": spread_mean, "threshold": lim_mean * 1.5, "direction": "above"})
        elif spread_mean > lim_mean:
            conf += 0.25
            evidence.append({"feature": "motor_spread_mean", "value": spread_mean, "threshold": lim_mean, "direction": "above"})

        if spread_std > 80 and roll_std < 4:
            conf += 0.1
        elif spread_std < 25 and roll_std > 10:
            failure = "pid_tuning_issue"
            conf += 0.25

        if not evidence: return None
        if conf < 0.55:
            return None
        conf = min(conf, 1.0)
        severity = "critical" if conf > 0.75 else "warning"
        
        return {
            "failure_type": failure, "confidence": conf, "severity": severity,
            "detection_method": "rule", "evidence": evidence,
            "recommendation": FAILURE_RECOMMENDATIONS.get(failure, "")
        }

    def _check_ekf(self, features):
        vv = features.get("ekf_vel_var_max", 0.0)
        pv = features.get("ekf_pos_var_max", 0.0)
        cv = features.get("ekf_compass_var_max", 0.0)
        ls = features.get("ekf_lane_switch_count", 0.0)
        fp = features.get("ekf_flags_error_pct", 0.0)
        
        # Raised threshold: compass_var > 1.0 fires too easily from motor EMI interference.
        # Real EKF failure needs 2+ variances high OR a lane switch.
        lim_fail = self.thresholds.get("ekf_variance_fail", 1.5)   # was 1.0
        lim_warn = lim_fail * 0.7  # ~1.05
        
        if vv <= lim_warn and pv <= lim_warn and cv <= lim_warn and ls == 0 and fp < 0.1:
            return None
            
        conf = 0.0
        evidence = []
        variances_over_fail = 0
        variances_over_warn = 0
        
        for name, val in [("ekf_vel_var", vv), ("ekf_pos_var", pv), ("ekf_compass_var", cv)]:
            if val > (lim_fail * 1.5):
                conf = max(conf, 0.85)
                variances_over_fail += 1
                evidence.append({"feature": f"{name}_max", "value": val, "threshold": lim_fail * 1.5, "direction": "above"})
            elif val > lim_fail:
                conf = max(conf, 0.65)
                variances_over_fail += 1
                evidence.append({"feature": f"{name}_max", "value": val, "threshold": lim_fail, "direction": "above"})
            elif val > lim_warn:
                variances_over_warn += 1

        if variances_over_warn >= 2:
            conf = max(conf, 0.55)
        if variances_over_fail >= 2:
            conf = max(conf, 0.90)

        if ls > 0:
            conf += 0.20
            evidence.append({"feature": "ekf_lane_switch_count", "value": ls, "threshold": 0, "direction": "above"})
        if fp > 0.1:
            conf += 0.10
            evidence.append({"feature": "ekf_flags_error_pct", "value": fp, "threshold": 0.1, "direction": "above"})

        conf = min(conf, 1.0)
        if conf == 0.0: return None
        
        # Require either: 2+ variances over fail threshold, OR a lane switch, OR very high single var
        if variances_over_fail < 2 and ls == 0 and (max(vv, pv, cv) < lim_fail * 1.5):
            return None  # Single moderate variance alone is not EKF failure

        return {
            "failure_type": "ekf_failure", "confidence": conf, "severity": "critical" if conf >= 0.8 else "warning",
            "detection_method": "rule", "evidence": evidence,
            "recommendation": FAILURE_RECOMMENDATIONS["ekf_failure"]
        }

    def _check_system(self, features):
        ll = features.get("sys_long_loops", 0.0)
        cpu = features.get("sys_cpu_load_mean", 0.0)
        ie = features.get("sys_internal_errors", 0.0)
        
        lim_ll = self.thresholds.get("long_loops_limit", 50)
        lim_cpu = self.thresholds.get("cpu_load_limit", 80)
        
        evidence = []
        conf = 0.0
        if ll > (lim_ll * 2):
            conf += 0.4
            evidence.append({"feature": "sys_long_loops", "value": ll, "threshold": lim_ll * 2, "direction": "above"})
        if cpu > (lim_cpu + 10):
            conf += 0.45
            evidence.append({"feature": "sys_cpu_load_mean", "value": cpu, "threshold": lim_cpu + 10, "direction": "above"})
        if ie > 0:
            conf += 0.7
            evidence.append({"feature": "sys_internal_errors", "value": ie, "threshold": 0, "direction": "above"})

        if not evidence: return None
        if ie <= 0 and len(evidence) < 2:
            return None
        conf = min(conf, 1.0)
        if conf < 0.7:
            return None
        severity = "critical" if conf > 0.85 else "warning"
        
        return {
            "failure_type": "mechanical_failure", "confidence": conf, "severity": severity,
            "detection_method": "rule", "evidence": evidence,
            "recommendation": "System load extremely high or internal errors. Software or companion computer issue."
        }

    def _check_rc_failsafe(self, features):
        """Detect RC failsafe events."""
        failsafe_count = features.get("evt_failsafe_count", 0.0)
        radio_failsafe = features.get("evt_radio_failsafe_count", 0.0)  # subsystem=5 (FAILSAFE_RADIO)
        rc_lost = features.get("evt_rc_lost_count", 0.0)  # MODE log: RTL/Land with reason=2
        
        if failsafe_count == 0 and radio_failsafe == 0 and rc_lost == 0:
            return None
            
        conf = 0.0
        evidence = []
        
        if radio_failsafe > 0:
            # Confirmed RC radio failsafe subsystem event
            conf = 0.90
            evidence.append({"feature": "evt_radio_failsafe_count", "value": radio_failsafe, "threshold": 0, "direction": "above"})
        elif failsafe_count > 0:
            # A generic failsafe happened — could be RC or battery.
            # Use moderate confidence since rule_engine will disambiguate on power features too
            conf = 0.65
            evidence.append({"feature": "evt_failsafe_count", "value": failsafe_count, "threshold": 0, "direction": "above"})
        if rc_lost > 0:
            conf = min(conf + 0.15, 1.0)
            evidence.append({"feature": "evt_rc_lost_count", "value": rc_lost, "threshold": 0, "direction": "above"})
            
        return {
            "failure_type": "rc_failsafe", "confidence": conf, "severity": "critical",
            "detection_method": "rule", "evidence": evidence,
            "recommendation": FAILURE_RECOMMENDATIONS.get("rc_failsafe", "RC signal lost. Check radio equipment and range.")
        }

    def _check_events(self, features):
        # Triggered when evt_crash_detected > 0 or evt_failsafe_count > 0
        crashes = features.get("evt_crash_detected", 0.0)
        failsafes = features.get("evt_failsafe_count", 0.0)
        auto_labels = features.get("auto_labels", features.get("_evt_auto_labels", []))
        
        if crashes == 0 and failsafes == 0 and not auto_labels: return None

        results = []
        if crashes >= 2 or (crashes > 0 and failsafes > 0):
            crash_conf = 0.85 if crashes >= 2 else 0.7
            results.append({
                "failure_type": "crash_unknown", "confidence": crash_conf, "severity": "critical" if crash_conf >= 0.8 else "warning",
                "detection_method": "rule", "evidence": [{"feature": "evt_crash_detected", "value": crashes, "threshold": 0, "direction": "above"}],
                "recommendation": FAILURE_RECOMMENDATIONS["crash_unknown"]
            })
            
        if auto_labels:
            for al in set(auto_labels):
                if al in FAILURE_RECOMMENDATIONS:
                    results.append({
                        "failure_type": al, "confidence": 0.78, "severity": "critical",
                        "detection_method": "rule", "evidence": [{"feature": "evt_auto_labels", "value": al, "threshold": "", "direction": "exact"}],
                        "recommendation": FAILURE_RECOMMENDATIONS[al]
                    })
                    
        # Return highest confidence or list of them? The design says return one diagnosis.
        # It's better to just return the most critical one. The caller function flattens the result.
        if results:
            results.sort(key=lambda x: x["confidence"], reverse=True)
            return results[0] # Returns only one, but theoretically we could expand this
            
        return None
