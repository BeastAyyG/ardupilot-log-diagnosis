import asyncio
import logging
import time
from typing import Any, cast

from fastapi import WebSocket
from pymavlink import mavutil

from src.contracts import ParsedLog
from src.features.pipeline import FeaturePipeline
from src.diagnosis.rule_engine import RuleEngine

LOGGER = logging.getLogger(__name__)

INTERESTING_MESSAGE_TYPES = {
    "VIBE", "MAG", "BAT", "CURR", "GPS", "RCOU", "XKF4", "NKF4",
    "PARM", "ERR", "EV", "MODE", "MSG", "CTUN", "ATT", "RATE",
    "PM", "FTN1", "IMU", "POWR"
}

# FIX 3: Max messages to drain per tick to prevent eval starvation
MAX_MSGS_PER_TICK = 100


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


class WebSocketManager:
    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)
        LOGGER.info(f"WebSocket client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            LOGGER.info(f"WebSocket client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict[str, Any]) -> None:
        dead_connections = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                dead_connections.append(connection)
        for connection in dead_connections:
            self.disconnect(connection)


class MAVLinkStreamer:
    def __init__(
        self,
        manager: WebSocketManager,
        connection_string: str,
        window_size: float = 30.0,
        eval_interval: float = 5.0,
    ) -> None:
        self.manager = manager
        self.connection_string = connection_string
        self.window_size = window_size
        self.eval_interval = eval_interval
        self.is_running = False
        self.task: asyncio.Task[Any] | None = None
        self.conn = None

    def start(self) -> None:
        if not self.is_running:
            self.is_running = True
            loop = asyncio.get_event_loop()
            self.task = loop.create_task(self._run_loop())
            LOGGER.info(f"Started MAVLink streamer for {self.connection_string}")

    def stop(self) -> None:
        self.is_running = False
        if self.task:
            self.task.cancel()
        if self.conn:
            self.conn.close()
            self.conn = None
        LOGGER.info("Stopped MAVLink streamer")

    async def _run_loop(self) -> None:
        try:
            LOGGER.info(f"Connecting to MAVLink at {self.connection_string}...")

            # FIX 6: Offload blocking mavlink_connection() to thread
            self.conn = await asyncio.to_thread(
                mavutil.mavlink_connection, self.connection_string
            )

            # FIX 2: Heartbeat wait inside try/finally so conn always closes
            heartbeat_wait_start = time.time()
            heartbeat = None
            while self.is_running and time.time() - heartbeat_wait_start < 30:
                heartbeat = self.conn.recv_match(type="HEARTBEAT", blocking=False)
                if heartbeat:
                    break
                await asyncio.sleep(0.1)

            if not heartbeat:
                LOGGER.error("Timeout waiting for heartbeat.")
                await self.manager.broadcast({
                    "type": "error",
                    "message": "Timeout waiting for heartbeat."
                })
                self.is_running = False
                return

            LOGGER.info(
                f"Heartbeat received: sys={heartbeat.get_srcSystem()} "
                f"comp={heartbeat.get_srcComponent()}"
            )
            await self.manager.broadcast({
                "type": "status",
                "message": "Connected and receiving telemetry."
            })

            messages_queue: list[dict[str, Any]] = []
            parameters: dict[str, Any] = {}
            vehicle_type = "Unknown"
            firmware_version = "Unknown"

            pipeline = FeaturePipeline()
            rule_engine = RuleEngine()
            last_eval_time = time.time()

            while self.is_running:
                current_time = time.time()

                # FIX 3: Bound drain loop to MAX_MSGS_PER_TICK
                msgs_read = 0
                while msgs_read < MAX_MSGS_PER_TICK:
                    msg = self.conn.recv_match(blocking=False)
                    if msg is None:
                        break

                    msgs_read += 1
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
                    if current_time - m["local_recv_time"] <= self.window_size
                ]

                if current_time - last_eval_time >= self.eval_interval:
                    last_eval_time = current_time

                    if messages_queue:
                        duration = (
                            messages_queue[-1]["local_recv_time"]
                            - messages_queue[0]["local_recv_time"]
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
                            features = await asyncio.to_thread(
                                pipeline.extract, parsed_data
                            )
                            diagnoses = await asyncio.to_thread(
                                rule_engine.diagnose, features
                            )
                            payload = {
                                "type": "evaluation",
                                "timestamp": time.time(),
                                "metadata": parsed_data["metadata"],
                                "features_summary": {
                                    k: v for k, v in features.items()
                                    if isinstance(v, (int, float, str, bool))
                                },
                                "diagnoses": diagnoses,
                            }
                            await self.manager.broadcast(payload)
                        except Exception as e:
                            LOGGER.warning(f"Error during live evaluation: {e}")

                await asyncio.sleep(0.01)

        except asyncio.CancelledError:
            LOGGER.info("MAVLink streamer task cancelled.")
        except Exception as e:
            LOGGER.exception(f"Unhandled exception in MAVLink streamer: {e}")
            await self.manager.broadcast({
                "type": "error",
                "message": f"Streamer crashed: {str(e)}"
            })
        finally:
            # FIX 2: Always close connection on ALL exit paths
            self.is_running = False
            if self.conn:
                self.conn.close()
                self.conn = None