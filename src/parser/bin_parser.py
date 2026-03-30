import logging
from typing import cast
from pymavlink import DFReader
from src.constants import ERR_SUBSYSTEM_MAP, ERR_AUTO_LABEL_MAP, MODE_NAMES, EV_NAMES
from src.contracts import ParsedLog


class LogParser:
    INTERESTING_MESSAGE_TYPES = {
        "VIBE",
        "MAG",
        "BAT",
        "CURR",  # pre-ArduCopter 4.0 battery messages (same fields as BAT)
        "GPS",
        "RCOU",
        "XKF4",
        "NKF4",
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
                "duration_sec": 0.0,
                "vehicle_type": "Unknown",
                "firmware_version": "Unknown",
                "total_messages": 0,
                "message_types": {},
            },
            "messages": {},
            "parameters": {},
            "errors": [],
            "events": [],
            "mode_changes": [],
            "status_messages": [],
        })

        try:
            log = DFReader.DFReader_binary(self.filepath)
        except Exception as e:
            self.logger.error(f"Failed to open log file {self.filepath}: {e}")
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
                        parsed_data["parameters"][name] = (
                            float(value) if isinstance(value, (int, float)) else value
                        )
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

        if first_time is not None and last_time is not None and last_time > first_time:
            parsed_data["metadata"]["duration_sec"] = (last_time - first_time) / 1e6

        if parsed_data["metadata"]["vehicle_type"] == "Unknown":
            parsed_data["metadata"]["vehicle_type"] = self._vehicle_from_parameters(
                parsed_data["parameters"]
            )

        return cast(ParsedLog, parsed_data)
