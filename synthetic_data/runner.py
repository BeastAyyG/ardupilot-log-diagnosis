"""Loopback-only MAVLink session used by the owned SITL executor."""

from __future__ import annotations

import ipaddress
import time
from collections.abc import Mapping
from typing import Any, Protocol

from pymavlink import mavutil

from .execution_integrity import float32_equal, runtime_identity

FRAME_CLASSES = {"quad": 1.0, "hexa": 2.0, "octa": 3.0}


class SITLSession(Protocol):
    endpoint: str

    def heartbeat(self, timeout: float) -> Mapping[str, Any]: ...

    def fetch_parameters(self, timeout: float) -> Mapping[str, float]: ...

    def wait_preflight_ready(self, timeout: float) -> None: ...

    def arm_and_takeoff(self, altitude_m: float, timeout: float) -> float: ...

    def wait_until_boot_ms(self, target_boot_ms: float, timeout: float) -> float: ...

    def set_parameter(
        self, name: str, value: float, timeout: float
    ) -> Mapping[str, Any]: ...

    def land_and_disarm(self, timeout: float) -> None: ...

    def is_armed(self, timeout: float = 2.0) -> bool: ...

    def force_disarm(self, timeout: float) -> None: ...

    def close(self) -> None: ...


class SITLProcessOwner(Protocol):
    binary_path: Any

    def finalize_log(self, timeout: float) -> tuple[Any, dict[str, Any]]: ...

    def abort(self, timeout: float) -> dict[str, Any]: ...


def validate_loopback_endpoint(endpoint: str) -> str:
    """Reject serial, broadcast, wildcard, hostname, and remote endpoints."""

    text = str(endpoint).strip()
    parts = text.split(":")
    if len(parts) != 3 or parts[0].lower() not in {
        "udp",
        "udpin",
        "tcp",
        "tcpin",
    }:
        raise ValueError(
            "endpoint must be udp/udpin/tcp/tcpin with an explicit loopback IP and port"
        )
    try:
        address = ipaddress.ip_address(parts[1])
        port = int(parts[2])
    except ValueError as exc:
        raise ValueError("endpoint contains an invalid loopback IP or port") from exc
    if not address.is_loopback:
        raise ValueError("the SITL executor only permits loopback endpoints")
    if not 1024 <= port <= 65535:
        raise ValueError("SITL endpoint port must be in the range 1024..65535")
    return f"{parts[0].lower()}:{address.compressed}:{port}"


class PymavlinkSITLSession:
    """Blocking adapter for one local ArduPilot SITL vehicle."""

    def __init__(self, endpoint: str):
        runtime_identity(enforce_supported_pymavlink=True)
        self.endpoint = validate_loopback_endpoint(endpoint)
        self.master = mavutil.mavlink_connection(
            self.endpoint,
            autoreconnect=False,
            source_system=255,
        )
        self._source_system: int | None = None
        self._source_component: int | None = None

    def _from_owned_vehicle(self, message: Any) -> bool:
        return (
            self._source_system is not None
            and self._source_component is not None
            and int(message.get_srcSystem()) == self._source_system
            and int(message.get_srcComponent()) == self._source_component
        )

    def heartbeat(self, timeout: float) -> Mapping[str, Any]:
        message = self.master.wait_heartbeat(timeout=timeout)
        if message is None:
            raise TimeoutError("SITL heartbeat was not received")
        if int(message.autopilot) != int(mavutil.mavlink.MAV_AUTOPILOT_ARDUPILOTMEGA):
            raise RuntimeError("heartbeat is not from ArduPilot")
        source_system = int(message.get_srcSystem())
        source_component = int(message.get_srcComponent())
        if source_system != 1 or source_component != int(
            mavutil.mavlink.MAV_COMP_ID_AUTOPILOT1
        ):
            raise RuntimeError("heartbeat source IDs differ from the owned instance")
        self._source_system = source_system
        self._source_component = source_component
        self.master.target_system = source_system
        self.master.target_component = source_component
        payload = dict(message.to_dict())
        payload["source_system"] = source_system
        payload["source_component"] = source_component
        return payload

    def fetch_parameters(self, timeout: float) -> Mapping[str, float]:
        self.master.mav.param_request_list_send(
            self.master.target_system,
            self.master.target_component,
        )
        values: dict[str, float] = {}
        expected: int | None = None
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            message = self.master.recv_match(
                type="PARAM_VALUE",
                blocking=True,
                timeout=1.0,
            )
            if message is None:
                if expected is not None and len(values) >= expected:
                    break
                continue
            if not self._from_owned_vehicle(message):
                continue
            name = str(message.param_id).rstrip("\x00")
            values[name] = float(message.param_value)
            expected = int(message.param_count)
            if expected > 0 and len(values) >= expected:
                break
        if expected is None or len(values) < expected:
            raise TimeoutError(
                f"parameter inventory incomplete: received {len(values)} of {expected or 0}"
            )
        return values

    def wait_preflight_ready(self, timeout: float) -> None:
        required = int(mavutil.mavlink.MAV_SYS_STATUS_SENSOR_3D_GYRO) | int(
            mavutil.mavlink.MAV_SYS_STATUS_SENSOR_3D_ACCEL
        )
        # The pinned inventory may deliberately leave MAVLink stream rates at
        # zero.  Request the health stream explicitly so readiness is based on
        # an observed SYS_STATUS frame, not on a missing-message timeout.
        self.master.mav.request_data_stream_send(
            self.master.target_system,
            self.master.target_component,
            mavutil.mavlink.MAV_DATA_STREAM_EXTENDED_STATUS,
            2,
            1,
        )
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            message = self.master.recv_match(
                type="SYS_STATUS",
                blocking=True,
                timeout=1.0,
            )
            if message is None or not self._from_owned_vehicle(message):
                continue
            enabled = int(message.onboard_control_sensors_enabled)
            healthy = int(message.onboard_control_sensors_health)
            if enabled & required == required and healthy & required == required:
                return
        raise TimeoutError("SITL did not report healthy gyro/accelerometer state")

    def _latest_boot_ms(self, timeout: float = 2.0) -> float:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            message = self.master.recv_match(
                type=["GLOBAL_POSITION_INT", "ATTITUDE"],
                blocking=True,
                timeout=min(1.0, max(0.0, deadline - time.monotonic())),
            )
            if (
                message is not None
                and self._from_owned_vehicle(message)
                and hasattr(message, "time_boot_ms")
            ):
                return float(message.time_boot_ms)
        raise TimeoutError("SITL boot-time telemetry was not received")

    @staticmethod
    def _heartbeat_armed(message: Any) -> bool:
        return bool(
            int(message.base_mode) & int(mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
        )

    def _wait_for_armed_state(self, expected: bool, timeout: float) -> None:
        """Wait with an explicit deadline; pymavlink's convenience waits have none."""

        deadline = time.monotonic() + timeout
        arm_rejection: str | None = None
        while time.monotonic() < deadline:
            message = self.master.recv_match(
                type=["HEARTBEAT", "COMMAND_ACK", "STATUSTEXT"],
                blocking=True,
                timeout=min(1.0, max(0.0, deadline - time.monotonic())),
            )
            if message is None or not self._from_owned_vehicle(message):
                continue
            get_type = getattr(message, "get_type", None)
            message_type = str(get_type()) if callable(get_type) else "HEARTBEAT"
            if message_type == "COMMAND_ACK":
                result = int(message.result)
                accepted = int(mavutil.mavlink.MAV_RESULT_ACCEPTED)
                if result != accepted:
                    arm_rejection = f"COMMAND_ACK result={result}"
            elif message_type == "STATUSTEXT":
                text = str(getattr(message, "text", "")).strip()
                if text:
                    arm_rejection = text
            elif self._heartbeat_armed(message) is expected:
                return
        state = "armed" if expected else "disarmed"
        if expected and arm_rejection:
            raise TimeoutError(f"SITL did not become {state}: {arm_rejection}")
        raise TimeoutError(f"SITL did not become {state}")

    def arm_and_takeoff(self, altitude_m: float, timeout: float) -> float:
        if not 2.0 <= altitude_m <= 30.0:
            raise ValueError("takeoff altitude must be in the range 2..30 metres")
        mode_id = self.master.mode_mapping().get("GUIDED")
        if mode_id is None:
            raise RuntimeError("SITL does not expose GUIDED mode")
        self.master.set_mode(mode_id)
        # A fresh SITL EEPROM may require accelerometer calibration before it
        # will accept arming.  Calibrate while the vehicle is stationary and
        # require an accepted command when ArduPilot reports an ACK.
        self.master.mav.command_long_send(
            self.master.target_system,
            self.master.target_component,
            mavutil.mavlink.MAV_CMD_PREFLIGHT_CALIBRATION,
            0,
            0,
            0,
            0,
            0,
            1,
            0,
            0,
        )
        calibration_deadline = time.monotonic() + min(5.0, max(0.1, timeout * 0.1))
        while time.monotonic() < calibration_deadline:
            message = self.master.recv_match(
                type=["COMMAND_ACK", "STATUSTEXT"],
                blocking=True,
                timeout=min(0.5, max(0.0, calibration_deadline - time.monotonic())),
            )
            if message is None or not self._from_owned_vehicle(message):
                continue
            get_type = getattr(message, "get_type", None)
            message_type = str(get_type()) if callable(get_type) else ""
            if message_type == "COMMAND_ACK" and int(message.command) == int(
                mavutil.mavlink.MAV_CMD_PREFLIGHT_CALIBRATION
            ):
                result = int(message.result)
                if result != int(mavutil.mavlink.MAV_RESULT_ACCEPTED):
                    raise RuntimeError(f"SITL accelerometer calibration rejected: result={result}")
                break
        self.master.arducopter_arm()
        self._wait_for_armed_state(True, timeout)
        self.master.mav.command_long_send(
            self.master.target_system,
            self.master.target_component,
            mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            float(altitude_m),
        )
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            message = self.master.recv_match(
                type="GLOBAL_POSITION_INT",
                blocking=True,
                timeout=1.0,
            )
            if (
                message is not None
                and self._from_owned_vehicle(message)
                and (float(message.relative_alt) / 1000.0 >= altitude_m * 0.8)
            ):
                return float(message.time_boot_ms)
        raise TimeoutError("SITL did not reach the takeoff altitude")

    def wait_until_boot_ms(self, target_boot_ms: float, timeout: float) -> float:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            current = self._latest_boot_ms()
            if current >= target_boot_ms:
                return current
        raise TimeoutError("SITL did not reach the planned simulation boot time")

    def _parameter_value(self, name: str, timeout: float) -> float:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            message = self.master.recv_match(
                type="PARAM_VALUE",
                blocking=True,
                timeout=1.0,
            )
            if message is None or not self._from_owned_vehicle(message):
                continue
            if str(message.param_id).rstrip("\x00") == name:
                return float(message.param_value)
        raise TimeoutError(f"SITL did not return parameter {name}")

    def set_parameter(
        self,
        name: str,
        value: float,
        timeout: float,
    ) -> Mapping[str, Any]:
        encoded = name.encode("ascii")
        send_boot_ms = self._latest_boot_ms()
        acknowledgement_value: float | None = None
        attempts = 0
        for attempts in range(1, 4):
            self.master.mav.param_set_send(
                self.master.target_system,
                self.master.target_component,
                encoded,
                float(value),
                mavutil.mavlink.MAV_PARAM_TYPE_REAL32,
            )
            try:
                acknowledgement_value = self._parameter_value(name, timeout / 3.0)
            except TimeoutError:
                continue
            if float32_equal(acknowledgement_value, value):
                break
        if acknowledgement_value is None:
            raise TimeoutError(f"SITL did not acknowledge parameter {name}")
        acknowledgement_boot_ms = self._latest_boot_ms()
        self.master.mav.param_request_read_send(
            self.master.target_system,
            self.master.target_component,
            encoded,
            -1,
        )
        explicit_readback = self._parameter_value(name, timeout)
        readback_boot_ms = self._latest_boot_ms()
        acknowledged = float32_equal(acknowledgement_value, value) and float32_equal(
            explicit_readback, value
        )
        return {
            "name": name,
            "requested": float(value),
            "ack_readback": acknowledgement_value,
            "readback": explicit_readback,
            "acknowledged": acknowledged,
            "send_boot_ms": send_boot_ms,
            "ack_boot_ms": acknowledgement_boot_ms,
            "readback_boot_ms": readback_boot_ms,
            "time_boot_ms": acknowledgement_boot_ms,
            "attempts": attempts,
            "target_system": int(self.master.target_system),
            "target_component": int(self.master.target_component),
        }

    def land_and_disarm(self, timeout: float) -> None:
        mode_id = self.master.mode_mapping().get("LAND")
        if mode_id is None:
            raise RuntimeError("SITL does not expose LAND mode")
        self.master.set_mode(mode_id)
        self._wait_for_armed_state(False, timeout)

    def is_armed(self, timeout: float = 2.0) -> bool:
        message = self.master.recv_match(
            type="HEARTBEAT",
            blocking=True,
            timeout=timeout,
        )
        if message is None or not self._from_owned_vehicle(message):
            raise TimeoutError("SITL armed state could not be determined")
        return self._heartbeat_armed(message)

    def force_disarm(self, timeout: float) -> None:
        self.master.arducopter_disarm()
        self._wait_for_armed_state(False, timeout)

    def close(self) -> None:
        self.master.close()


def execute_run(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Compatibility import for the owned-process executor."""

    from .executor import execute_run as implementation

    return implementation(*args, **kwargs)
