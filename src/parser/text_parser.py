"""ArduPilot DataFlash text-log adapter using pymavlink's DFReader_text."""

from __future__ import annotations

from typing import cast
from pathlib import Path

from pymavlink import DFReader

from src.constants import ERR_AUTO_LABEL_MAP, ERR_SUBSYSTEM_MAP, EV_NAMES, MODE_NAMES
from src.contracts import ParsedLog
from src.diagnosis.log_quality import LogQualityEngine
from src.parser.file_format import detect_file_format


class TextLogParser:
    def __init__(self, filepath: str):
        self.filepath = filepath

    @staticmethod
    def _vehicle_from_message(message_text: str) -> tuple[str, str | None]:
        mappings = {"ArduCopter": "Copter", "ArduPlane": "Plane", "ArduRover": "Rover", "APMrover2": "Rover", "ArduSub": "Sub"}
        parts = (message_text or "").split()
        for token, vehicle in mappings.items():
            if token in message_text:
                return vehicle, parts[1] if len(parts) > 1 and parts[0] == token else None
        return "Unknown", None

    def parse(self) -> ParsedLog:
        parsed = cast(ParsedLog, {"metadata": {"filepath": self.filepath, "file_format": detect_file_format(self.filepath, hash_file=True), "duration_sec": 0.0, "vehicle_type": "Unknown", "firmware_version": "Unknown", "total_messages": 0, "message_types": {}, "parse_complete": False, "parse_error": None}, "messages": {}, "parameters": {}, "errors": [], "events": [], "mode_changes": [], "status_messages": [], "parameter_changes": []})
        log = None
        first_time: float | None = None
        last_time: float | None = None
        try:
            if Path(self.filepath).stat().st_size == 0:
                parsed["metadata"]["parse_error"] = "Text log is empty."
            else:
                log = DFReader.DFReader_text(self.filepath)
                while True:
                    message = log.recv_msg()
                    if message is None:
                        break
                    message_type = message.get_type()
                    parsed["metadata"]["total_messages"] += 1
                    parsed["metadata"]["message_types"][message_type] = parsed["metadata"]["message_types"].get(message_type, 0) + 1
                    values = message.to_dict()
                    parsed["messages"].setdefault(message_type, []).append(values)
                    timestamp = getattr(message, "TimeUS", values.get("TimeUS"))
                    if isinstance(timestamp, (int, float)):
                        first_time = float(timestamp) if first_time is None else first_time
                        last_time = float(timestamp)
                    if message_type == "MSG":
                        text = str(values.get("Message", ""))
                        parsed["status_messages"].append({"time_us": timestamp, "message": text})
                        vehicle, version = self._vehicle_from_message(text)
                        if vehicle != "Unknown":
                            parsed["metadata"]["vehicle_type"] = vehicle
                        if version:
                            parsed["metadata"]["firmware_version"] = version
                    elif message_type == "PARM":
                        name, value = values.get("Name"), values.get("Value")
                        if name is not None and value is not None:
                            if name in parsed["parameters"] and parsed["parameters"][name] != value:
                                parsed["parameter_changes"].append({"time_us": timestamp, "name": name, "old_value": parsed["parameters"][name], "new_value": value})
                            parsed["parameters"][name] = value
                    elif message_type == "ERR":
                        subsystem = values.get("Subsys", values.get("SubSystem"))
                        code = values.get("ECode", values.get("Code"))
                        parsed["errors"].append({"time_us": timestamp, "subsystem": subsystem, "subsystem_name": ERR_SUBSYSTEM_MAP.get(subsystem, "UNKNOWN"), "code": code, "code_name": ERR_AUTO_LABEL_MAP.get(subsystem, "UNKNOWN")})
                    elif message_type == "EV":
                        event_id = values.get("Id", values.get("Event"))
                        parsed["events"].append({"time_us": timestamp, "event": event_id, "name": EV_NAMES.get(event_id, "UNKNOWN")})
                    elif message_type == "MODE":
                        mode = values.get("Mode", values.get("ModeNum"))
                        try:
                            mode_number = int(mode)
                        except (TypeError, ValueError):
                            mode_number = None
                        parsed["mode_changes"].append({"time_us": timestamp, "mode": mode_number if mode_number is not None else mode, "mode_name": MODE_NAMES.get(mode_number, str(mode) if mode is not None else "UNKNOWN")})
                parsed["metadata"]["duration_sec"] = max(0.0, ((last_time or 0.0) - (first_time or 0.0)) / 1e6)
                parsed["metadata"]["parse_complete"] = True
        except Exception as exc:
            parsed["metadata"]["parse_error"] = str(exc)
        finally:
            if log is not None:
                close = getattr(log, "close", None)
                if callable(close):
                    close()
        try:
            parsed["metadata"]["quality_report"] = LogQualityEngine().evaluate(parsed)
        except Exception:
            parsed["metadata"]["quality_report"] = {"overall_status": "DEGRADED", "capabilities": {}, "actionable_recommendations": []}
        return parsed
