import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import yaml

from .failure_types import FailureType, get_failure_definition


DEFAULT_THRESHOLDS: Dict[str, Dict[str, Dict[str, float]]] = {
    "default": {
        "vibration": {
            "max_warn": 30.0,
            "max_critical": 60.0,
            "clip_warn": 1.0,
            "clip_critical": 80.0,
        },
        "compass": {
            "range_warn": 220.0,
            "range_critical": 420.0,
            "std_warn": 80.0,
            "std_critical": 160.0,
        },
        "battery": {
            "volt_min_warn": 10.8,
            "volt_min_critical": 9.8,
            "volt_range_warn": 1.0,
            "volt_range_critical": 2.0,
            "curr_max_warn": 45.0,
            "curr_max_critical": 65.0,
        },
        "gps": {
            "fix_pct_warn": 90.0,
            "fix_pct_critical": 70.0,
            "nsats_min_warn": 8.0,
            "nsats_min_critical": 5.0,
            "hdop_max_warn": 2.5,
            "hdop_max_critical": 4.0,
        },
        "motor": {
            "spread_mean_warn": 120.0,
            "spread_mean_critical": 220.0,
            "spread_max_warn": 220.0,
            "spread_max_critical": 350.0,
            "output_std_warn": 90.0,
            "output_std_critical": 150.0,
        },
        "attitude": {
            "roll_std_warn": 8.0,
            "roll_std_critical": 15.0,
            "pitch_std_warn": 8.0,
            "pitch_std_critical": 15.0,
            "roll_max_warn": 30.0,
            "roll_max_critical": 45.0,
            "pitch_max_warn": 30.0,
            "pitch_max_critical": 45.0,
            "desroll_err_warn": 10.0,
            "desroll_err_critical": 20.0,
        },
    },
    "copter": {
        "attitude": {
            "roll_std_warn": 7.0,
            "roll_std_critical": 13.0,
            "pitch_std_warn": 7.0,
            "pitch_std_critical": 13.0,
        }
    },
    "plane": {
        "gps": {"fix_pct_warn": 92.0, "fix_pct_critical": 75.0},
        "vibration": {"max_warn": 35.0, "max_critical": 70.0},
    },
    "rover": {
        "attitude": {"roll_max_warn": 22.0, "roll_max_critical": 35.0},
        "gps": {"nsats_min_warn": 6.0, "nsats_min_critical": 4.0},
    },
    "sub": {
        "gps": {"fix_pct_warn": 0.0, "fix_pct_critical": 0.0},
        "compass": {"range_warn": 260.0, "range_critical": 500.0},
    },
}


@dataclass
class RuleDiagnosis:
    failure_type: str
    confidence: float
    evidence: List[str]
    fix: str
    severity: str

    def to_dict(self) -> dict:
        return {
            "failure_type": self.failure_type,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "fix": self.fix,
            "severity": self.severity,
        }


class RuleEngine:
    """Threshold-based failure detection with per-vehicle profile support."""

    def __init__(self, thresholds_path: Optional[str] = None, vehicle_profile: Optional[str] = None, min_confidence: float = 0.35):
        self.thresholds_path = thresholds_path or os.path.join(
            os.path.dirname(__file__), "config", "thresholds.yaml"
        )
        self.thresholds = self._load_thresholds()
        self.vehicle_profile = (vehicle_profile or "default").lower()
        self.min_confidence = min_confidence

    def diagnose(self, features: dict, metadata: Optional[dict] = None) -> list:
        """
        Run all rules against features.
        Returns list of RuleDiagnosis objects.
        """
        profile = self._resolve_profile(metadata)

        checks = [
            self._check_vibration(features, profile),
            self._check_compass(features, profile),
            self._check_battery(features, profile),
            self._check_gps(features, profile),
            self._check_motor(features, profile),
            self._check_attitude(features, profile),
        ]

        results = [r for r in checks if r and r.confidence >= self.min_confidence]
        results.sort(key=lambda r: r.confidence, reverse=True)
        return results

    def _resolve_profile(self, metadata: Optional[dict]) -> str:
        if self.vehicle_profile != "default":
            return self.vehicle_profile

        vehicle = (metadata or {}).get("vehicle_type", "default")
        vehicle = str(vehicle).strip().lower()
        return vehicle if vehicle in self.thresholds else "default"

    def _load_thresholds(self) -> Dict[str, Dict[str, Dict[str, float]]]:
        thresholds = self._deep_copy_thresholds(DEFAULT_THRESHOLDS)
        if not os.path.exists(self.thresholds_path):
            return thresholds

        with open(self.thresholds_path, "r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}

        if not isinstance(loaded, dict):
            return thresholds

        for profile, profile_rules in loaded.items():
            profile_key = str(profile).lower()
            if not isinstance(profile_rules, dict):
                continue
            thresholds.setdefault(profile_key, {})
            for rule_name, values in profile_rules.items():
                if not isinstance(values, dict):
                    continue
                thresholds[profile_key].setdefault(rule_name, {})
                thresholds[profile_key][rule_name].update(values)

        return thresholds

    def _deep_copy_thresholds(self, src: Dict[str, Dict[str, Dict[str, float]]]) -> Dict[str, Dict[str, Dict[str, float]]]:
        copied: Dict[str, Dict[str, Dict[str, float]]] = {}
        for profile, rules in src.items():
            copied[profile] = {}
            for rule_name, values in rules.items():
                copied[profile][rule_name] = dict(values)
        return copied

    def _rule_cfg(self, profile: str, rule_name: str) -> Dict[str, float]:
        cfg = dict(self.thresholds.get("default", {}).get(rule_name, {}))
        cfg.update(self.thresholds.get(profile, {}).get(rule_name, {}))
        return cfg

    def _severity_ratio(self, value: float, warn: float, critical: float, higher_is_worse: bool) -> float:
        if warn == critical:
            return 0.0

        if higher_is_worse:
            if value <= warn:
                return 0.0
            if value >= critical:
                return 1.0
            return (value - warn) / (critical - warn)

        # lower-is-worse
        if value >= warn:
            return 0.0
        if value <= critical:
            return 1.0
        return (warn - value) / (warn - critical)

    def _confidence_from_ratios(self, ratios: List[float]) -> float:
        active = [r for r in ratios if r > 0.0]
        if not active:
            return 0.0
        max_ratio = max(active)
        return min(1.0, 0.30 + (0.50 * max_ratio) + 0.08 * (len(active) - 1))

    def _severity_from_confidence(self, confidence: float) -> str:
        if confidence >= 0.90:
            return "critical"
        if confidence >= 0.70:
            return "high"
        if confidence >= 0.50:
            return "medium"
        return "low"

    def _num(self, features: Dict[str, Any], key: str) -> float:
        value = features.get(key, 0.0)
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _build_diagnosis(self, failure_type: FailureType, confidence: float, evidence: List[str]) -> RuleDiagnosis:
        definition = get_failure_definition(failure_type)
        return RuleDiagnosis(
            failure_type=failure_type.value,
            confidence=min(max(float(confidence), 0.0), 1.0),
            evidence=evidence,
            fix=definition.fix,
            severity=self._severity_from_confidence(confidence),
        )

    def _check_vibration(self, features: Dict[str, Any], profile: str) -> Optional[RuleDiagnosis]:
        cfg = self._rule_cfg(profile, "vibration")
        v_x = self._num(features, "vibe_x_max")
        v_y = self._num(features, "vibe_y_max")
        v_z = self._num(features, "vibe_z_max")
        clip = self._num(features, "vibe_clip_total")
        vmax = max(v_x, v_y, v_z)

        ratios = [
            self._severity_ratio(vmax, cfg["max_warn"], cfg["max_critical"], higher_is_worse=True),
            self._severity_ratio(clip, cfg["clip_warn"], cfg["clip_critical"], higher_is_worse=True),
        ]
        confidence = self._confidence_from_ratios(ratios)
        if confidence <= 0.0:
            return None

        evidence = []
        if vmax > cfg["max_warn"]:
            evidence.append(f"vibration_peak={vmax:.2f} (warn>{cfg['max_warn']}, critical>{cfg['max_critical']})")
        if clip > cfg["clip_warn"]:
            evidence.append(f"vibration_clip_total={clip:.2f} (warn>{cfg['clip_warn']}, critical>{cfg['clip_critical']})")
        return self._build_diagnosis(FailureType.VIBRATION_HIGH, confidence, evidence)

    def _check_compass(self, features: Dict[str, Any], profile: str) -> Optional[RuleDiagnosis]:
        cfg = self._rule_cfg(profile, "compass")
        mag_range = self._num(features, "mag_field_range")
        mag_std = self._num(features, "mag_field_std")

        ratios = [
            self._severity_ratio(mag_range, cfg["range_warn"], cfg["range_critical"], higher_is_worse=True),
            self._severity_ratio(mag_std, cfg["std_warn"], cfg["std_critical"], higher_is_worse=True),
        ]
        confidence = self._confidence_from_ratios(ratios)
        if confidence <= 0.0:
            return None

        evidence = []
        if mag_range > cfg["range_warn"]:
            evidence.append(f"mag_field_range={mag_range:.2f} (warn>{cfg['range_warn']}, critical>{cfg['range_critical']})")
        if mag_std > cfg["std_warn"]:
            evidence.append(f"mag_field_std={mag_std:.2f} (warn>{cfg['std_warn']}, critical>{cfg['std_critical']})")
        return self._build_diagnosis(FailureType.COMPASS_INTERFERENCE, confidence, evidence)

    def _check_battery(self, features: Dict[str, Any], profile: str) -> Optional[RuleDiagnosis]:
        cfg = self._rule_cfg(profile, "battery")
        volt_min = self._num(features, "bat_volt_min")
        volt_range = self._num(features, "bat_volt_range")
        curr_max = self._num(features, "bat_curr_max")

        ratios = [
            self._severity_ratio(volt_min, cfg["volt_min_warn"], cfg["volt_min_critical"], higher_is_worse=False),
            self._severity_ratio(volt_range, cfg["volt_range_warn"], cfg["volt_range_critical"], higher_is_worse=True),
            self._severity_ratio(curr_max, cfg["curr_max_warn"], cfg["curr_max_critical"], higher_is_worse=True),
        ]
        confidence = self._confidence_from_ratios(ratios)
        if confidence <= 0.0:
            return None

        evidence = []
        if volt_min < cfg["volt_min_warn"]:
            evidence.append(f"bat_volt_min={volt_min:.2f}V (warn<{cfg['volt_min_warn']}, critical<{cfg['volt_min_critical']})")
        if volt_range > cfg["volt_range_warn"]:
            evidence.append(
                f"bat_volt_range={volt_range:.2f}V (warn>{cfg['volt_range_warn']}, critical>{cfg['volt_range_critical']})"
            )
        if curr_max > cfg["curr_max_warn"]:
            evidence.append(f"bat_curr_max={curr_max:.2f}A (warn>{cfg['curr_max_warn']}, critical>{cfg['curr_max_critical']})")
        return self._build_diagnosis(FailureType.BATTERY_SAG, confidence, evidence)

    def _check_gps(self, features: Dict[str, Any], profile: str) -> Optional[RuleDiagnosis]:
        cfg = self._rule_cfg(profile, "gps")

        # Submersibles may disable GPS checks by setting warn/critical to zero.
        if cfg.get("fix_pct_warn", 0.0) <= 0 and cfg.get("fix_pct_critical", 0.0) <= 0:
            return None

        fix_pct = self._num(features, "gps_fix_pct")
        nsats_min = self._num(features, "gps_nsats_min")
        hdop_max = self._num(features, "gps_hdop_max")

        ratios = [
            self._severity_ratio(fix_pct, cfg["fix_pct_warn"], cfg["fix_pct_critical"], higher_is_worse=False),
            self._severity_ratio(nsats_min, cfg["nsats_min_warn"], cfg["nsats_min_critical"], higher_is_worse=False),
            self._severity_ratio(hdop_max, cfg["hdop_max_warn"], cfg["hdop_max_critical"], higher_is_worse=True),
        ]
        confidence = self._confidence_from_ratios(ratios)
        if confidence <= 0.0:
            return None

        evidence = []
        if fix_pct < cfg["fix_pct_warn"]:
            evidence.append(f"gps_fix_pct={fix_pct:.2f}% (warn<{cfg['fix_pct_warn']}, critical<{cfg['fix_pct_critical']})")
        if nsats_min < cfg["nsats_min_warn"]:
            evidence.append(f"gps_nsats_min={nsats_min:.2f} (warn<{cfg['nsats_min_warn']}, critical<{cfg['nsats_min_critical']})")
        if hdop_max > cfg["hdop_max_warn"]:
            evidence.append(f"gps_hdop_max={hdop_max:.2f} (warn>{cfg['hdop_max_warn']}, critical>{cfg['hdop_max_critical']})")
        return self._build_diagnosis(FailureType.GPS_DEGRADATION, confidence, evidence)

    def _check_motor(self, features: Dict[str, Any], profile: str) -> Optional[RuleDiagnosis]:
        cfg = self._rule_cfg(profile, "motor")
        spread_mean = self._num(features, "motor_spread_mean")
        spread_max = self._num(features, "motor_spread_max")
        output_std = self._num(features, "motor_output_std")

        ratios = [
            self._severity_ratio(spread_mean, cfg["spread_mean_warn"], cfg["spread_mean_critical"], higher_is_worse=True),
            self._severity_ratio(spread_max, cfg["spread_max_warn"], cfg["spread_max_critical"], higher_is_worse=True),
            self._severity_ratio(output_std, cfg["output_std_warn"], cfg["output_std_critical"], higher_is_worse=True),
        ]
        confidence = self._confidence_from_ratios(ratios)
        if confidence <= 0.0:
            return None

        evidence = []
        if spread_mean > cfg["spread_mean_warn"]:
            evidence.append(
                f"motor_spread_mean={spread_mean:.2f} (warn>{cfg['spread_mean_warn']}, critical>{cfg['spread_mean_critical']})"
            )
        if spread_max > cfg["spread_max_warn"]:
            evidence.append(f"motor_spread_max={spread_max:.2f} (warn>{cfg['spread_max_warn']}, critical>{cfg['spread_max_critical']})")
        if output_std > cfg["output_std_warn"]:
            evidence.append(f"motor_output_std={output_std:.2f} (warn>{cfg['output_std_warn']}, critical>{cfg['output_std_critical']})")
        return self._build_diagnosis(FailureType.MOTOR_IMBALANCE, confidence, evidence)

    def _check_attitude(self, features: Dict[str, Any], profile: str) -> Optional[RuleDiagnosis]:
        cfg = self._rule_cfg(profile, "attitude")
        roll_std = self._num(features, "att_roll_std")
        pitch_std = self._num(features, "att_pitch_std")
        roll_max = abs(self._num(features, "att_roll_max"))
        pitch_max = abs(self._num(features, "att_pitch_max"))
        desroll_err = self._num(features, "att_desroll_err")

        ratios = [
            self._severity_ratio(roll_std, cfg["roll_std_warn"], cfg["roll_std_critical"], higher_is_worse=True),
            self._severity_ratio(pitch_std, cfg["pitch_std_warn"], cfg["pitch_std_critical"], higher_is_worse=True),
            self._severity_ratio(roll_max, cfg["roll_max_warn"], cfg["roll_max_critical"], higher_is_worse=True),
            self._severity_ratio(pitch_max, cfg["pitch_max_warn"], cfg["pitch_max_critical"], higher_is_worse=True),
            self._severity_ratio(desroll_err, cfg["desroll_err_warn"], cfg["desroll_err_critical"], higher_is_worse=True),
        ]
        confidence = self._confidence_from_ratios(ratios)
        if confidence <= 0.0:
            return None

        evidence = []
        if roll_std > cfg["roll_std_warn"]:
            evidence.append(f"att_roll_std={roll_std:.2f} (warn>{cfg['roll_std_warn']}, critical>{cfg['roll_std_critical']})")
        if pitch_std > cfg["pitch_std_warn"]:
            evidence.append(f"att_pitch_std={pitch_std:.2f} (warn>{cfg['pitch_std_warn']}, critical>{cfg['pitch_std_critical']})")
        if roll_max > cfg["roll_max_warn"]:
            evidence.append(f"att_roll_max={roll_max:.2f} (warn>{cfg['roll_max_warn']}, critical>{cfg['roll_max_critical']})")
        if pitch_max > cfg["pitch_max_warn"]:
            evidence.append(f"att_pitch_max={pitch_max:.2f} (warn>{cfg['pitch_max_warn']}, critical>{cfg['pitch_max_critical']})")
        if desroll_err > cfg["desroll_err_warn"]:
            evidence.append(
                f"att_desroll_err={desroll_err:.2f} (warn>{cfg['desroll_err_warn']}, critical>{cfg['desroll_err_critical']})"
            )
        return self._build_diagnosis(FailureType.ATTITUDE_INSTABILITY, confidence, evidence)
