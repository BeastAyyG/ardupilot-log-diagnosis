"""
live_stream.py — Async MAVLink listener, rolling-window feature extraction,
WebSocket fan-out broadcaster, and per-evaluation diagnosis.

Bug fixes applied
-----------------
Bug 1  : start() was a plain `def` but called asyncio.create_task() — made async.
Bug 5  : Window pruning now uses a monotonic wall-clock baseline anchored to the
         first received message, so replays / SIL sources with time_boot_ms == 0
         are handled correctly without evicting every message immediately.

Production hardening
--------------------
Hardening 1 : WebSocketManager.ping_all() sends periodic WebSocket pings so
              silently-dropped clients (network blip, no close frame) are detected
              proactively rather than only during the next broadcast.
Hardening 2 : MAVLinkStreamer._run_loop() schedules a ping task via
              asyncio.create_task() and cancels it cleanly on shutdown.
"""

from __future__ import annotations

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
    "PM", "FTN1", "IMU", "POWR",
}

# How often (seconds) to ping all connected WebSocket clients to detect
# silently-dropped connections before the next evaluation broadcast.
PING_INTERVAL_SEC: float = 20.0


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
        LOGGER.info(
            "WebSocket client connected. Total clients: %d",
            len(self.active_connections),
        )

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            LOGGER.info(
                "WebSocket client disconnected. Total clients: %d",
                len(self.active_connections),
            )

    async def broadcast(self, message: dict[str, Any]) -> None:
        dead_connections: list[WebSocket] = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                dead_connections.append(connection)
        for connection in dead_connections:
            self.disconnect(connection)

    # ── Hardening 1: ping_all() ──────────────────────────────────────────────
    # Sends a lightweight JSON ping to every connected client.  Clients that
    # have silently dropped (network blip, no TCP FIN/RST) raise an exception
    # here and are removed immediately — before the next real broadcast —
    # so the active_connections list stays accurate at all times.
    # Called on a fixed interval (PING_INTERVAL_SEC) from a background task
    # inside MAVLinkStreamer._run_loop().
    async def ping_all(self) -> None:
        dead_connections: list[WebSocket] = []
        for connection in self.active_connections:
            try:
                await connection.send_json({"type": "ping"})
            except Exception:
                dead_connections.append(connection)
        for connection in dead_connections:
            LOGGER.info("Removing silently-dead WebSocket client during ping sweep.")
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
        # ── Hardening 2: separate task for periodic keepalive pings ──────────
        self.ping_task: asyncio.Task[Any] | None = None
        self.conn = None

    # ── Bug 1 fix: was `def start(self)` — must be async so callers can
    #    `await` it and asyncio.create_task() receives a real coroutine. ──────
    async def start(self) -> None:
        if not self.is_running:
            self.is_running = True
            self.task = asyncio.create_task(self._run_loop())
            # ── Hardening 2: launch the ping keepalive loop as a sibling task.
            self.ping_task = asyncio.create_task(self._ping_loop())
            LOGGER.info("Started MAVLink streamer for %s", self.connection_string)

    def stop(self) -> None:
        self.is_running = False
        if self.task:
            self.task.cancel()
        # ── Hardening 2: also cancel the sibling ping keepalive task ─────────
        if self.ping_task:
            self.ping_task.cancel()
        if self.conn:
            self.conn.close()
        LOGGER.info("Stopped MAVLink streamer")

    # ── Hardening 2: _ping_loop() ────────────────────────────────────────────
    # Runs as an independent asyncio task.  Every PING_INTERVAL_SEC it asks
    # WebSocketManager to sweep all active connections with a JSON ping so that
    # silently-dead clients are reaped promptly, keeping active_connections
    # accurate even between evaluation broadcasts.
    async def _ping_loop(self) -> None:
        try:
            while self.is_running:
                await asyncio.sleep(PING_INTERVAL_SEC)
                if self.manager.active_connections:
                    await self.manager.ping_all()
        except asyncio.CancelledError:
            LOGGER.info("Ping keepalive task cancelled.")
        except Exception as exc:
            LOGGER.warning("Unexpected error in ping loop: %s", exc)

    async def _run_loop(self) -> None:
        try:
            LOGGER.info(
                "Connecting to MAVLink stream at %s...", self.connection_string
            )
            self.conn = mavutil.mavlink_connection(self.connection_string)

            # Wait for heartbeat non-blocking
            heartbeat_wait_start = time.monotonic()
            heartbeat = None
            while self.is_running and time.monotonic() - heartbeat_wait_start < 30:
                heartbeat = self.conn.recv_match(type="HEARTBEAT", blocking=False)
                if heartbeat:
                    break
                await asyncio.sleep(0.1)

            if not heartbeat:
                LOGGER.error("Timeout waiting for heartbeat. Check connection.")
                await self.manager.broadcast(
                    {"type": "error", "message": "Timeout waiting for heartbeat."}
                )
                self.is_running = False
                return

            LOGGER.info(
                "Heartbeat received: src_sys=%d, src_comp=%d",
                heartbeat.get_srcSystem(),
                heartbeat.get_srcComponent(),
            )
            await self.manager.broadcast(
                {"type": "status", "message": "Connected and receiving telemetry."}
            )

            messages_queue: list[dict[str, Any]] = []
            parameters: dict[str, Any] = {}
            vehicle_type = "Unknown"
            firmware_version = "Unknown"

            pipeline = FeaturePipeline()
            rule_engine = RuleEngine()

            last_eval_time = time.monotonic()

            # ── Bug 5 fix: anchor the rolling window to the wall-clock time of
            #    the *first* received message, not to absolute time.time().
            #    This way replays / SIL sources whose time_boot_ms starts at 0
            #    are not immediately evicted by the pruning step. ──────────────
            window_anchor: float | None = None

            while self.is_running:
                current_time = time.monotonic()
                msgs_read = 0

                # Drain the receive queue without blocking the event loop
                while msgs_read < 100:
                    msg = self.conn.recv_match(blocking=False)
                    if msg is None:
                        break

                    msgs_read += 1
                    msg_type = msg.get_type()
                    msg_time = time.monotonic()

                    # Anchor the window clock to the first message received
                    if window_anchor is None:
                        window_anchor = msg_time

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

                        messages_queue.append(
                            {
                                "local_recv_time": msg_time,
                                "type": df_msg_type,
                                "dict": msg_dict,
                            }
                        )

                # Prune messages outside the rolling window using the anchored
                # monotonic clock so SIL / replay sources are handled correctly.
                if window_anchor is not None:
                    cutoff = current_time - self.window_size
                    messages_queue = [
                        m for m in messages_queue
                        if m["local_recv_time"] >= cutoff
                    ]

                if current_time - last_eval_time >= self.eval_interval:
                    last_eval_time = current_time

                    if messages_queue:
                        duration = (
                            messages_queue[-1]["local_recv_time"]
                            - messages_queue[0]["local_recv_time"]
                            if len(messages_queue) > 1
                            else 0.0
                        )

                        parsed_data = cast(
                            ParsedLog,
                            {
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
                            },
                        )

                        for m in messages_queue:
                            m_type = m["type"]
                            m_dict = m["dict"]
                            parsed_data["metadata"]["message_types"][m_type] = (
                                parsed_data["metadata"]["message_types"].get(m_type, 0) + 1
                            )
                            if m_type not in parsed_data["messages"]:
                                parsed_data["messages"][m_type] = []
                            parsed_data["messages"][m_type].append(m_dict)

                        try:
                            # Run heavy work in a thread so the asyncio loop is not blocked
                            features = await asyncio.to_thread(
                                pipeline.extract, parsed_data
                            )
                            diagnoses = await asyncio.to_thread(
                                rule_engine.diagnose, features
                            )

                            # Derive a simple decision summary from diagnoses so the
                            # front-end does not have to hard-code "healthy".
                            decision = {
                                "status": "confirmed" if diagnoses else "healthy",
                                "top_guess": diagnoses[0]["failure_type"] if diagnoses else "nominal",
                                "top_confidence": diagnoses[0].get("confidence", 0.0) if diagnoses else 0.0,
                                "ranked_subsystems": [],
                                "rationale": [],
                                "requires_human_review": len(diagnoses) > 0,
                            }

                            payload = {
                                "type": "evaluation",
                                "timestamp": time.time(),
                                "metadata": parsed_data["metadata"],
                                "features_summary": {
                                    k: v
                                    for k, v in features.items()
                                    if isinstance(v, (int, float, str, bool))
                                },
                                "diagnoses": diagnoses,
                                # Bug 4 fix: expose decision so the front-end
                                # does not hard-code a misleading "healthy" status.
                                "decision": decision,
                            }
                            await self.manager.broadcast(payload)

                        except Exception as exc:
                            LOGGER.warning("Error during live evaluation: %s", exc)

                await asyncio.sleep(0.01)

        except asyncio.CancelledError:
            LOGGER.info("MAVLink streamer task cancelled.")
        except Exception as exc:
            LOGGER.exception("Unhandled exception in MAVLink streamer: %s", exc)
            await self.manager.broadcast(
                {"type": "error", "message": f"Streamer crashed: {exc}"}
            )
        finally:
            self.is_running = False
            if self.conn:
                self.conn.close()
                self.conn = None