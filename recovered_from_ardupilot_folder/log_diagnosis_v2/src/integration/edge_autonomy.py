from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional


class GuardState(str, Enum):
    SAFE = "safe"
    WARN = "warn"
    VERIFY = "verify"
    ACTION = "action"


@dataclass
class GuardDecision:
    state: GuardState
    command: str
    risk_score: float
    reason: str
    consecutive_high: int
    consecutive_safe: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state.value,
            "command": self.command,
            "risk_score": self.risk_score,
            "reason": self.reason,
            "consecutive_high": self.consecutive_high,
            "consecutive_safe": self.consecutive_safe,
        }


class GuardedFailsafeStateMachine:
    """
    Warn -> Verify -> Act flow to avoid one-shot autonomous actions.
    """

    def __init__(
        self,
        warn_threshold: float = 0.45,
        verify_threshold: float = 0.65,
        action_threshold: float = 0.80,
        verify_samples: int = 3,
        cooldown_samples: int = 3,
    ):
        self.warn_threshold = warn_threshold
        self.verify_threshold = verify_threshold
        self.action_threshold = action_threshold
        self.verify_samples = verify_samples
        self.cooldown_samples = cooldown_samples

        self.state = GuardState.SAFE
        self.consecutive_high = 0
        self.consecutive_safe = 0

    def update(self, risk_score: float, anomaly_type: str = "none") -> GuardDecision:
        risk_score = float(max(0.0, min(1.0, risk_score)))

        if risk_score >= self.verify_threshold:
            self.consecutive_high += 1
            self.consecutive_safe = 0
        elif risk_score <= self.warn_threshold:
            self.consecutive_safe += 1
            self.consecutive_high = 0
        else:
            self.consecutive_high = 0
            self.consecutive_safe = 0

        if risk_score >= self.action_threshold and self.consecutive_high >= self.verify_samples:
            self.state = GuardState.ACTION
            command = "set_mode_rtl"
            reason = f"risk {risk_score:.2f} sustained for {self.consecutive_high} cycles ({anomaly_type})"
        elif risk_score >= self.verify_threshold:
            self.state = GuardState.VERIFY
            command = "hold_position_and_recheck"
            reason = f"risk {risk_score:.2f} above verify threshold ({anomaly_type})"
        elif risk_score >= self.warn_threshold:
            self.state = GuardState.WARN
            command = "pilot_warning"
            reason = f"risk {risk_score:.2f} above warn threshold ({anomaly_type})"
        elif self.consecutive_safe >= self.cooldown_samples:
            self.state = GuardState.SAFE
            command = "none"
            reason = f"risk normalized for {self.consecutive_safe} cycles"
        else:
            # Hold SAFE if not enough samples to fully cool down.
            self.state = GuardState.SAFE
            command = "none"
            reason = "risk below warning threshold"

        return GuardDecision(
            state=self.state,
            command=command,
            risk_score=risk_score,
            reason=reason,
            consecutive_high=self.consecutive_high,
            consecutive_safe=self.consecutive_safe,
        )


def _estimate_battery_pct(voltage: float) -> int:
    if voltage <= 0.0:
        return 0
    # 3S LiPo approximation for telemetry display use only.
    pct = int((voltage - 10.0) / (12.6 - 10.0) * 100)
    return max(0, min(100, pct))


def report_to_legacy_payload(
    report: Dict[str, Any],
    drone_id: str = "drone_01",
    connection: str = "online",
    location: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    diagnoses = report.get("diagnoses", [])
    top = diagnoses[0] if diagnoses else {}
    features = report.get("features", {})

    risk_score = float(top.get("confidence", 0.0))
    anomaly_type = str(top.get("type", "none")) if top else "none"
    confidence = float(top.get("confidence", 0.99 if not diagnoses else 0.0))

    volt_for_pct = float(features.get("bat_volt_min", 0.0))

    payload = {
        "drone_id": drone_id,
        "timestamp_ms": int(report.get("timestamp_ms", 0)) or 0,
        "status": {
            "connection": connection,
            "ai_active": True,
            "battery_pct": _estimate_battery_pct(volt_for_pct),
        },
        "inference": {
            "risk_score": risk_score,
            "anomaly_type": anomaly_type if diagnoses else "none",
            "confidence": confidence,
        },
        "physics": {
            "roll": float(features.get("att_roll_max", 0.0)),
            "pitch": float(features.get("att_pitch_max", 0.0)),
            "vibe_x": float(features.get("vibe_x_max", 0.0)),
        },
    }

    if location is not None:
        payload["location"] = {
            "lat": float(location.get("lat", 0.0)),
            "lon": float(location.get("lon", 0.0)),
            "alt": float(location.get("alt", 0.0)),
        }

    return payload
