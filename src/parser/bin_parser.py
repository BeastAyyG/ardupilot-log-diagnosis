import logging
import re
from typing import cast
from pymavlink import DFReader
from src.constants import ERR_SUBSYSTEM_MAP, ERR_AUTO_LABEL_MAP, MODE_NAMES, EV_NAMES
from src.contracts import ParsedLog
from src.diagnosis.log_quality import LogQualityEngine
from src.parser.file_format import detect_file_format


class LogParser:
    INTERESTING_MESSAGE_TYPES = {
        "VIBE",
        "MAG",
        "BAT",
        "CURR",  # pre-ArduCopter 4.0 battery messages (same fields as BAT)
        "GPS",
        "BARO",
        "ARSP",
        "ESC",
        "RPM",
        "RCIN",
        "RCOU",
        "MOT",
        "SERVO",
        "BAT2",
        "BAT3",
        "GPS2",
        "GPS3",
        "AHR2",
        "POS",
        "STAT",
        "CMD",
        "FENCE",
        "RALLY",
        "FILE",
        "ORGN",
        "HOME",
        "XKF4",
        "XKF1",
        "XKF2",
        "XKF3",
        "XKF5",
        "NKF4",
        "NKF1",
        "NKF2",
        "NKF3",
        "NKF5",
        "IMU2",
        "IMU3",
        "PIDR",
        "PIDP",
        "PIDY",
        "PIQR",
        "PIQP",
        "PIQY",
        "PIDS",
        "PIDA",
        "PIDT",
        "PTUN",  # detailed PID tuning telemetry on newer firmware
        "PARM",
        "ERR",
        "EV",
        "MODE",
        "MSG",
        "CTUN",
        "ATT",
        "RATE",  # PID controller: desired vs actual rates for tuning diagnosis
        "PM",
        "FTN1",
        "IMU",
        "POWR",
    }

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def _vehicle_from_message(message_text: str) -> tuple[str, str | None]:
        message_text = message_text or ""
        mappings = {
            "ArduCopter": "Copter",
            "ArduPlane": "Plane",
            "ArduRover": "Rover",
            "APMrover2": "Rover",
            "ArduSub": "Sub",
        }
        for token, vehicle_type in mappings.items():
            if token in message_text:
                parts = message_text.split()
                version = None
                if len(parts) > 1 and parts[0] == token:
                    version = parts[1]
                return vehicle_type, version
        return "Unknown", None

    @staticmethod
    def _vehicle_from_parameters(parameters: dict) -> str:
        frame_class = parameters.get("FRAME_CLASS")
        if frame_class is not None:
            return "Copter"
        if "SKID_STEER_OUT" in parameters or "CRUISE_SPEED" in parameters:
            return "Rover"
        if "Q_ENABLE" in parameters:
            return "Plane"
        if "SURFACE_DEPTH" in parameters or "WPNAV_SPEED_DN" in parameters:
            return "Sub"
        return "Unknown"

    def parse(self) -> ParsedLog:
        """
        Parse entire .BIN file.
        Returns a dict containing metadata, messages, parameters, errors, events,
        mode_changes, and status_messages.
        """
        parsed_data = cast(ParsedLog, {
            "metadata": {
                "filepath": self.filepath,
                "file_format": None,
                "duration_sec": 0.0,
                "vehicle_type": "Unknown",
                "firmware_version": "Unknown",
                "firmware_hash": "Unknown",
                "board": "Unknown",
                "total_messages": 0,
                "message_types": {},
                "parse_complete": False,
                "parse_error": None,
            },
            "messages": {},
            "parameters": {},
            "errors": [],
            "events": [],
            "mode_changes": [],
            "status_messages": [],
            "parameter_changes": [],
        })

        try:
            parsed_data["metadata"]["file_format"] = detect_file_format(self.filepath, hash_file=True)
        except Exception as exc:
            # Keep the parser's historical best-effort contract for callers
            # that use synthetic/fake paths in tests; the quality report will
            # expose the missing file/signature as a degraded input.
            parsed_data["metadata"]["parse_error"] = str(exc)

        detected_format = parsed_data["metadata"].get("file_format", {}) or {}
        if detected_format.get("format") == "px4_ulog":
            from src.parser.ulog_parser import ULogParser

            return ULogParser(self.filepath).parse()
        if detected_format.get("format") == "mavlink_tlog":
            from src.parser.tlog_parser import TLogParser

            return TLogParser(self.filepath).parse()
        if detected_format.get("format") == "text_log":
            from src.parser.text_parser import TextLogParser

            return TextLogParser(self.filepath).parse()
        if detected_format.get("format") == "betaflight_bbl":
            from src.parser.bbl_parser import BBLParser

            return BBLParser(self.filepath).parse()

        try:
            log = DFReader.DFReader_binary(self.filepath)
        except Exception as e:
            self.logger.error(f"Failed to open log file {self.filepath}: {e}")
            parsed_data["metadata"]["parse_error"] = str(e)
            return cast(ParsedLog, parsed_data)

        first_time = None
        last_time = None

        try:
            while True:
                msg = log.recv_msg()
                if msg is None:
                    break

                msg_type = msg.get_type()

                # Metadata
                parsed_data["metadata"]["total_messages"] += 1
                parsed_data["metadata"]["message_types"][msg_type] = (
                    parsed_data["metadata"]["message_types"].get(msg_type, 0) + 1
                )

                time_us = getattr(msg, "TimeUS", None)
                if time_us is not None:
                    if first_time is None:
                        first_time = time_us
                    last_time = time_us

                if msg_type in self.INTERESTING_MESSAGE_TYPES:
                    if msg_type not in parsed_data["messages"]:
                        parsed_data["messages"][msg_type] = []

                    # Convert message fields to Python native types (dictionary)
                    msg_dict = msg.to_dict()
                    parsed_data["messages"][msg_type].append(msg_dict)
                else:
                    msg_dict = None

                if msg_type == "MSG" and msg_dict:
                    message_text = msg_dict.get("Message", "")
                    parsed_data["status_messages"].append(
                        {"time_us": time_us, "message": message_text}
                    )
                    vehicle_type, firmware_version = self._vehicle_from_message(
                        message_text
                    )
                    if vehicle_type != "Unknown":
                        parsed_data["metadata"]["vehicle_type"] = vehicle_type
                    if firmware_version:
                        parsed_data["metadata"]["firmware_version"] = firmware_version
                elif msg_type == "PARM" and msg_dict:
                    name = msg_dict.get("Name")
                    value = msg_dict.get("Value")
                    if name is not None and value is not None:
                        normalized_value = (
                            float(value) if isinstance(value, (int, float)) else value
                        )
                        if name in parsed_data["parameters"] and parsed_data["parameters"][name] != normalized_value:
                            parsed_data["parameter_changes"].append(
                                {
                                    "time_us": time_us,
                                    "name": name,
                                    "old_value": parsed_data["parameters"][name],
                                    "new_value": normalized_value,
                                }
                            )
                        parsed_data["parameters"][name] = normalized_value
                elif msg_type == "ERR" and msg_dict:
                    subsys = msg_dict.get("Subsys", 0)
                    ecode = msg_dict.get("ECode", 0)
                    subsys_name = ERR_SUBSYSTEM_MAP.get(subsys, f"UNKNOWN_{subsys}")
                    auto_label = ERR_AUTO_LABEL_MAP.get(subsys)
                    if subsys == 11 and ecode != 2:
                        auto_label = None  # special condition for GPS
                    parsed_data["errors"].append(
                        {
                            "time_us": time_us,
                            "subsystem": subsys,
                            "subsystem_name": subsys_name,
                            "code": ecode,
                            "auto_label": auto_label,
                        }
                    )
                elif msg_type == "EV" and msg_dict:
                    ev_id = msg_dict.get("Id", 0)
                    ev_name = EV_NAMES.get(ev_id, f"EVENT_{ev_id}")
                    parsed_data["events"].append(
                        {"time_us": time_us, "id": ev_id, "name": ev_name}
                    )
                elif msg_type == "MODE" and msg_dict:
                    mode_num = msg_dict.get("ModeNum", msg_dict.get("Mode", 0))
                    reason = msg_dict.get("Reason", 0)
                    mode_name = MODE_NAMES.get(mode_num, f"MODE_{mode_num}")
                    parsed_data["mode_changes"].append(
                        {
                            "time_us": time_us,
                            "mode": mode_num,
                            "mode_name": mode_name,
                            "reason": reason,
                        }
                    )

        except Exception as e:
            self.logger.warning(
                f"Error or log truncated while reading messages from {self.filepath}: {e}"
            )
            parsed_data["metadata"]["parse_error"] = str(e)

        parsed_data["metadata"]["parse_complete"] = parsed_data["metadata"].get("parse_error") is None

        if first_time is not None and last_time is not None and last_time > first_time:
            parsed_data["metadata"]["duration_sec"] = (last_time - first_time) / 1e6

        if parsed_data["metadata"]["vehicle_type"] == "Unknown":
            parsed_data["metadata"]["vehicle_type"] = self._vehicle_from_parameters(
                parsed_data["parameters"]
            )

        # MSG records are the authoritative offline source for firmware/build
        # and board identity when a full hardware connection is unavailable.
        for status in parsed_data["status_messages"]:
            text = str(status.get("message", ""))
            firmware_match = re.search(r"\b(?:ArduCopter|ArduPlane|ArduRover|ArduSub)\s+(V?\d+(?:\.\d+)+)(?:\s+\(([0-9A-Fa-f]+)\))?", text)
            if firmware_match:
                parsed_data["metadata"]["firmware_version"] = firmware_match.group(1)
                if firmware_match.group(2):
                    parsed_data["metadata"]["firmware_hash"] = firmware_match.group(2)
            board_match = re.search(r"\b(fmuv\d+|Cube\w*|Pixhawk\w*|Durandal\w*|Kakute\w*|Matek\w*)\b", text, re.IGNORECASE)
            if board_match:
                parsed_data["metadata"]["board"] = board_match.group(1)

        try:
            parsed_data["metadata"]["quality_report"] = LogQualityEngine().evaluate(parsed_data)
        except Exception as exc:
            self.logger.warning(f"Error evaluating log quality: {exc}")
            parsed_data["metadata"]["quality_report"] = {
                "overall_status": "UNKNOWN",
                "duration_sec": parsed_data["metadata"].get("duration_sec", 0.0),
                "total_messages": parsed_data["metadata"].get("total_messages", 0),
                "capabilities": {},
                "actionable_recommendations": [],
            }

        return cast(ParsedLog, parsed_data)
