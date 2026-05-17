from __future__ import annotations

import time
import logging
from argparse import _SubParsersAction
from typing import cast

from pymavlink import mavutil
from src.contracts import ParsedLog
from src.features.pipeline import FeaturePipeline
from src.diagnosis.rule_engine import RuleEngine
from src.cli.formatter import DiagnosisFormatter

logger = logging.getLogger(__name__)


def register(subparsers: _SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "live", help="Connect to a live MAVLink stream and run diagnostics in real-time"
    )
    parser.add_argument(
        "connection", help="MAVLink connection string (e.g., tcp:127.0.0.1:5760, /dev/ttyUSB0)"
    )
    parser.add_argument(
        "--window", type=float, default=30.0, help="Rolling window size in seconds"
    )
    parser.add_argument(
        "--interval", type=float, default=5.0, help="Diagnostic evaluation interval in seconds"
    )
    parser.set_defaults(func=run)


def run(args) -> None:
    connection_string = args.connection
    window_size = args.window
    eval_interval = args.interval

    print(f"Connecting to {connection_string}...")
    try:
        conn = mavutil.mavlink_connection(connection_string)
    except Exception as e:
        print(f"Failed to connect: {e}")
        return

    print("Waiting for heartbeat...")
    heartbeat = conn.recv_match(type="HEARTBEAT", blocking=True, timeout=30)
    if heartbeat is None:
        print("Timeout waiting for heartbeat. Check connection and vehicle power.")
        return

    print(f"Heartbeat received from system {heartbeat.get_srcSystem()} component {heartbeat.get_srcComponent()}")

    messages_queue = []
    parameters = {}
    vehicle_type = "Unknown"
    firmware_version = "Unknown"

    pipeline = FeaturePipeline()
    rule_engine = RuleEngine()
    formatter = DiagnosisFormatter()

    last_eval_time = time.time()

    INTERESTING_MESSAGE_TYPES = {
        "VIBE", "MAG", "BAT", "CURR", "GPS", "RCOU", "XKF4", "NKF4",
        "PARM", "ERR", "EV", "MODE", "MSG", "CTUN", "ATT", "RATE",
        "PM", "FTN1", "IMU", "POWR"
    }

    def vehicle_from_heartbeat(mav_type: int) -> str:
        if mav_type in (2, 3, 4, 13, 14, 15):
            return "Copter"
        elif mav_type == 1:
            return "Plane"
        elif mav_type == 10:
            return "Rover"
        elif mav_type == 12:
            return "Sub"
        return "Unknown"

    print("Listening for messages. Press Ctrl+C to stop.")
    try:
        while True:
            current_time = time.time()

            while True:
                msg = conn.recv_match(blocking=False)
                if msg is None:
                    break

                msg_type = msg.get_type()
                msg_time = time.time()

                if msg_type == "HEARTBEAT" and vehicle_type == "Unknown":
                    vehicle_type = vehicle_from_heartbeat(msg.type)

                if msg_type == "AUTOPILOT_VERSION":
                    major = (msg.flight_sw_version >> 24) & 0xFF
                    minor = (msg.flight_sw_version >> 16) & 0xFF
                    patch = (msg.flight_sw_version >> 8) & 0xFF
                    firmware_version = f"{major}.{minor}.{patch}"

                if msg_type == "PARAM_VALUE":
                    param_id = msg.param_id
                    if isinstance(param_id, bytes):
                        param_id = param_id.decode("utf-8").rstrip("\x00")
                    parameters[param_id] = msg.param_value

                if msg_type in INTERESTING_MESSAGE_TYPES or msg_type == "STATUSTEXT":
                    msg_dict = msg.to_dict()
                    if "time_boot_ms" in msg_dict:
                        msg_dict["TimeUS"] = msg_dict["time_boot_ms"] * 1000
                    elif "time_usec" in msg_dict:
                        msg_dict["TimeUS"] = msg_dict["time_usec"]
                    else:
                        msg_dict["TimeUS"] = int(msg_time * 1e6)

                    df_msg_type = msg_type
                    if msg_type == "STATUSTEXT":
                        df_msg_type = "MSG"
                        msg_dict["Message"] = msg_dict.get("text", "")

                    messages_queue.append({
                        "local_recv_time": msg_time,
                        "type": df_msg_type,
                        "dict": msg_dict
                    })

            messages_queue = [
                m for m in messages_queue
                if current_time - m["local_recv_time"] <= window_size
            ]

            if current_time - last_eval_time >= eval_interval:
                last_eval_time = current_time

                if not messages_queue:
                    continue

                duration = (
                    messages_queue[-1]["local_recv_time"] - messages_queue[0]["local_recv_time"]
                    if len(messages_queue) > 1 else 0.0
                )

                parsed_data = cast(ParsedLog, {
                    "metadata": {
                        "filepath": "live_stream",
                        "duration_sec": duration,
                        "vehicle_type": vehicle_type,
                        "firmware_version": firmware_version,
                        "total_messages": len(messages_queue),
                        "message_types": {},
                    },
                    "messages": {},
                    "parameters": parameters.copy(),
                    "errors": [],
                    "events": [],
                    "mode_changes": [],
                    "status_messages": [],
                })

                for m in messages_queue:
                    m_type = m["type"]
                    m_dict = m["dict"]
                    parsed_data["metadata"]["message_types"][m_type] = \
                        parsed_data["metadata"]["message_types"].get(m_type, 0) + 1
                    if m_type not in parsed_data["messages"]:
                        parsed_data["messages"][m_type] = []
                    parsed_data["messages"][m_type].append(m_dict)

                try:
                    features = pipeline.extract(parsed_data)
                    diagnoses = rule_engine.diagnose(features)
                    alert_diagnoses = [
                        d for d in diagnoses
                        if d.get("severity") in ("warning", "critical")
                    ]
                    if alert_diagnoses:
                        print(f"\n--- Diagnoses at {time.strftime('%H:%M:%S')} ---")
                        output = formatter.format_terminal(
                            alert_diagnoses,
                            features.get("_metadata", {}),
                            decision=None,
                            similar_cases=[],
                            runtime_info={"engine": "rule", "ml_available": False, "ml_reason": "live mode"},
                            parameter_warnings=[],
                            explain_data=None
                        )
                        print(output)
                except Exception as e:
                    logger.warning(f"Error during live evaluation: {e}")

            time.sleep(0.01)

    except KeyboardInterrupt:
        print("\nStopping live diagnosis.")
    finally:
        conn.close()
