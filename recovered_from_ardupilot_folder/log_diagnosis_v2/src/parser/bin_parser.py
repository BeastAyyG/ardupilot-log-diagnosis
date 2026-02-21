import os
from pymavlink import mavutil


class LogParser:
    """Parse ArduPilot .BIN log files into structured data."""

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.metadata = {}
        self.messages = {}
        self._connection = None

    def parse(self) -> dict:
        """Parse entire log file. Returns structured dict."""
        if not os.path.exists(self.filepath):
            raise FileNotFoundError(f"Log file not found: {self.filepath}")

        self._connection = mavutil.mavlink_connection(self.filepath)

        self.metadata = {
            "duration_s": 0,
            "vehicle_type": "Unknown",
            "firmware_version": "Unknown",
            "board_type": "Unknown",
            "total_messages": 0,
        }

        start_time_us = None
        end_time_us = None

        while True:
            msg = self._connection.recv_match(blocking=False)
            if msg is None:
                break

            msg_type = msg.get_type()

            if msg_type == "BAD_DATA":
                continue

            self.metadata["total_messages"] += 1

            if msg_type not in self.messages:
                self.messages[msg_type] = []

            msg_dict = msg.to_dict()
            self.messages[msg_type].append(msg_dict)

            # Extract metadata from MSG
            if msg_type == "MSG":
                text = msg_dict.get("Message", "")
                if "V" in text and (
                    "ArduCopter" in text or "ArduPlane" in text or "ArduRover" in text or "ArduSub" in text
                ):
                    self.metadata["firmware_version"] = text
                    if "Copter" in text:
                        self.metadata["vehicle_type"] = "Copter"
                    elif "Plane" in text:
                        self.metadata["vehicle_type"] = "Plane"
                    elif "Rover" in text:
                        self.metadata["vehicle_type"] = "Rover"
                    elif "Sub" in text:
                        self.metadata["vehicle_type"] = "Sub"

            # Time tracking for duration
            if "TimeUS" in msg_dict:
                time_us = msg_dict["TimeUS"]
                if start_time_us is None or time_us < start_time_us:
                    start_time_us = time_us
                if end_time_us is None or time_us > end_time_us:
                    end_time_us = time_us

        if start_time_us is not None and end_time_us is not None:
            self.metadata["duration_s"] = (end_time_us - start_time_us) / 1e6

        return {"metadata": self.metadata, "messages": self.messages}

    def get_messages(self, msg_type: str) -> list:
        """Get all messages of a specific type."""
        return self.messages.get(msg_type, [])

    def get_metadata(self) -> dict:
        """Extract log metadata: duration, vehicle, FW version."""
        return self.metadata

    def get_time_range(self) -> tuple:
        """Return (start_time_ms, end_time_ms)."""
        start_time_us = None
        end_time_us = None

        for msg_list in self.messages.values():
            for msg in msg_list:
                if "TimeUS" in msg:
                    time_us = msg["TimeUS"]
                    if start_time_us is None or time_us < start_time_us:
                        start_time_us = time_us
                    if end_time_us is None or time_us > end_time_us:
                        end_time_us = time_us

        if start_time_us is not None and end_time_us is not None:
            return (start_time_us / 1000.0, end_time_us / 1000.0)
        return (0.0, 0.0)

    def get_parameter(self, param_name: str):
        """Read a specific parameter value from PARM messages."""
        parm_msgs = self.get_messages("PARM")
        for msg in parm_msgs:
            if msg.get("Name", "") == param_name:
                return msg.get("Value", None)
        return None
