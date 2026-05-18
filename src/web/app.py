"""
app.py — FastAPI application entry-point.

Bug fixes applied
-----------------
Bug 1 : streamer.start() is now async, so we pass it directly to
        asyncio.create_task() instead of wrapping it in get_event_loop().
Bug 2 : Removed all asyncio.get_event_loop() calls inside async functions;
        replaced with asyncio.create_task() / asyncio.get_running_loop() as
        appropriate (Python 3.10+ deprecation).
Bug 3 : /api/live/connect now validates the auth token (query-param `token`)
        so unauthenticated callers cannot trigger arbitrary MAVLink connections.
Bug 6 : Added asyncio.Lock (_connect_lock) around the connect/stop endpoints
        to prevent a race condition when two clients click Connect simultaneously.
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, ValidationError

from src.web.schemas import AnalysisResponse, ChatRequest, ChatResponse

from src.diagnosis.decision_policy import evaluate_decision
from src.diagnosis.hybrid_engine import HybridEngine
from src.diagnosis.parameter_validation import validate_parameters
from src.diagnosis.rule_engine import RuleEngine
from src.features.pipeline import FeaturePipeline
from src.parser.bin_parser import LogParser
from src.chat.assistant import ChatAssistant
from src.comparison.trend_analyzer import TrendAnalyzer
from src.web.live_stream import WebSocketManager, MAVLinkStreamer


LOGGER = logging.getLogger(__name__)
MAX_UPLOAD_BYTES = 64 * 1024 * 1024
UPLOAD_CHUNK_SIZE = 1024 * 1024
WEB_DIR = Path(__file__).parent.absolute()

ws_manager = WebSocketManager()
streamer: MAVLinkStreamer | None = None

# Bug 6 fix: single lock so concurrent /connect or /stop requests are serialised
# and cannot create duplicate streamers or cause use-after-free on `streamer`.
_connect_lock: asyncio.Lock = asyncio.Lock()


# ── Bug 1 & 2 fix: use lifespan context manager (replaces deprecated
#    @app.on_event).  asyncio.create_task() is called directly — no
#    get_event_loop() needed inside an async context. ─────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────────────
    global streamer
    mavlink_conn = os.environ.get("MAVLINK_CONNECTION")
    if mavlink_conn:
        streamer = MAVLinkStreamer(ws_manager, mavlink_conn)
        # start() is now async, so create_task() receives a real coroutine.
        asyncio.create_task(streamer.start())

    yield  # ── Application runs here ─────────────────────────────────────────

    # ── Shutdown ─────────────────────────────────────────────────────────────
    if streamer and streamer.is_running:
        streamer.stop()


app = FastAPI(title="ArduPilot Log Diagnosis API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ConnectRequest(BaseModel):
    connection_string: str


def _get_expected_token() -> str:
    return os.environ.get("MAVLINK_AUTH_TOKEN", "ardupilot")


# ── Bug 3 fix: added `token` query parameter; returns 403 when it does not
#    match MAVLINK_AUTH_TOKEN so unauthenticated callers cannot trigger an
#    arbitrary MAVLink connection.
# ── Bug 2 fix: asyncio.get_event_loop() replaced with asyncio.create_task().
# ── Bug 6 fix: entire body is executed under _connect_lock. ─────────────────
@app.post("/api/live/connect")
async def connect_live_stream(
    req: ConnectRequest,
    token: str = Query(default=""),
):
    if token != _get_expected_token():
        raise HTTPException(status_code=403, detail="Invalid or missing auth token.")

    async with _connect_lock:
        global streamer
        if streamer and streamer.is_running:
            streamer.stop()
        streamer = MAVLinkStreamer(ws_manager, req.connection_string)
        # Bug 1 & 2 fix: start() is async; create_task() used directly.
        asyncio.create_task(streamer.start())

    return {"status": "started", "connection_string": req.connection_string}


@app.post("/api/live/stop")
async def stop_live_stream():
    async with _connect_lock:
        global streamer
        if streamer and streamer.is_running:
            streamer.stop()
            return {"status": "stopped"}
    return {"status": "already_stopped"}


@app.websocket("/api/live/stream")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(default="")):
    if token != _get_expected_token():
        await websocket.close(code=1008)
        return

    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep the connection alive; actual data is pushed via broadcast()
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


@app.get("/", response_class=HTMLResponse)
async def get_index() -> str:
    index_path = WEB_DIR / "index.html"
    if index_path.exists():
        return index_path.read_text(encoding="utf-8")
    return "UI not found"


@app.post("/api/analyze", response_model=AnalysisResponse)
async def analyze_log(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".bin"):
        return JSONResponse(
            status_code=400, content={"error": "Only .BIN files are supported."}
        )

    fd, temp_path = tempfile.mkstemp(suffix=".bin")
    try:
        total_bytes = 0
        with os.fdopen(fd, "wb") as handle:
            while True:
                chunk = await file.read(UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > MAX_UPLOAD_BYTES:
                    return JSONResponse(
                        status_code=413,
                        content={
                            "error": f"Uploaded file exceeds {MAX_UPLOAD_BYTES} bytes."
                        },
                    )
                handle.write(chunk)

        result = await asyncio.to_thread(_analyze_temp_log, temp_path, file.filename)
        return AnalysisResponse(**result)
    except ValidationError as e:
        LOGGER.exception("Schema validation failed for model output")
        return JSONResponse(
            status_code=500,
            content={"error": "Schema validation failed", "details": e.errors()},
        )
    except Exception:
        LOGGER.exception("Error during analysis")
        return JSONResponse(
            status_code=500,
            content={"error": "Analysis failed. Check server logs for details."},
        )
    finally:
        await file.close()
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except PermissionError:
                pass


def _analyze_temp_log(temp_path: str, original_filename: str) -> dict[str, Any]:
    parser = LogParser(temp_path)
    parsed = parser.parse()

    pipeline = FeaturePipeline()
    features = pipeline.extract(parsed)

    engine = HybridEngine()
    diagnoses = engine.diagnose(features)
    explain_data = dict(getattr(engine, "last_explain_data", {}))
    parameter_warnings = validate_parameters(
        parsed.get("parameters", {}),
        features,
        features.get("_metadata", {}).get("vehicle_type", "Unknown"),
    )

    decision = evaluate_decision(diagnoses)
    explain_data["decision"] = decision

    time_series, timeline_events = _build_visualization_data(parsed, features)
    rule_diagnoses = RuleEngine().diagnose(features)
    rule_output_only = rule_diagnoses[0]["failure_type"] if rule_diagnoses else "nominal"

    return {
        "metadata": {
            "filename": original_filename,
            "duration": features.get("_metadata", {}).get("duration_sec", 0),
            "vehicle": features.get("_metadata", {}).get("vehicle_type", "Unknown"),
        },
        "features": features,
        "diagnoses": diagnoses,
        "parameter_warnings": parameter_warnings,
        "explain_data": explain_data,
        "time_series": time_series,
        "timeline_events": timeline_events,
        "rule_output_only": rule_output_only,
        "rule_output_diagnoses": rule_diagnoses,
    }


def _build_visualization_data(
    parsed: dict[str, Any], features: dict[str, Any]
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    time_series: dict[str, list[dict[str, Any]]] = {"gps": [], "vibe": []}
    start_time = _find_start_time_us(parsed)

    vibe_msgs = parsed.get("messages", {}).get("VIBE", [])
    gps_msgs = parsed.get("messages", {}).get("GPS", [])

    vibe_times = [msg.get("TimeUS") for msg in vibe_msgs if msg.get("TimeUS") is not None]
    gps_times = [msg.get("TimeUS") for msg in gps_msgs if msg.get("TimeUS") is not None]
    if vibe_times and start_time is not None:
        log_end_time_s = (vibe_times[-1] - start_time) / 1e6
    elif gps_times and start_time is not None:
        log_end_time_s = (gps_times[-1] - start_time) / 1e6
    else:
        log_end_time_s = features.get("_metadata", {}).get("duration_sec", 0)

    step = max(1, len(vibe_msgs) // 500)
    for msg in vibe_msgs[::step]:
        t_us = msg.get("TimeUS")
        if t_us is None:
            continue
        if start_time is None:
            start_time = t_us
        time_series["vibe"].append(
            {
                "t": round((t_us - start_time) / 1e6, 2),
                "x": msg.get("VibeX", 0),
                "y": msg.get("VibeY", 0),
                "z": msg.get("VibeZ", 0),
            }
        )

    step_gps = max(1, len(gps_msgs) // 500)
    for msg in gps_msgs[::step_gps]:
        lat = msg.get("Lat")
        lng = msg.get("Lng")
        alt = msg.get("Alt", 0)
        t_us = msg.get("TimeUS")
        if lat and lng and lat != 0 and lng != 0 and t_us is not None:
            if start_time is None:
                start_time = t_us
            time_series["gps"].append(
                {
                    "t": round((t_us - start_time) / 1e6, 2),
                    "lat": lat / 1e7,
                    "lng": lng / 1e7,
                    "alt": alt,
                }
            )

    def get_gps_at(t_target: float) -> dict[str, Any] | None:
        if not time_series["gps"]:
            return None
        return min(time_series["gps"], key=lambda point: abs(point["t"] - t_target))

    timeline_events: list[dict[str, Any]] = []
    err_label_map = {
        3: ("Compass Error", "critical"),
        5: ("Radio Failsafe", "critical"),
        6: ("Battery Failsafe", "critical"),
        11: ("GPS Glitch", "warning"),
        12: ("Crash Detected", "crash"),
        16: ("EKF Check Failed", "critical"),
        17: ("EKF Failsafe", "crash"),
        25: ("Thrust Loss", "critical"),
        29: ("Vibration Failsafe", "critical"),
    }
    for err in parsed.get("errors", []):
        t_us = err.get("time_us")
        if t_us is None or start_time is None:
            continue
        t_s = round((t_us - start_time) / 1e6, 2)
        subsys = err.get("subsystem", 0)
        label, severity = err_label_map.get(
            subsys, (err.get("subsystem_name", "Error"), "warning")
        )
        timeline_events.append(
            {
                "t_sec": t_s,
                "type": "error",
                "label": label,
                "severity": severity,
                "gps": get_gps_at(t_s),
            }
        )

    for mc in parsed.get("mode_changes", []):
        t_us = mc.get("time_us")
        if t_us is None or start_time is None:
            continue
        t_s = round((t_us - start_time) / 1e6, 2)
        timeline_events.append(
            {
                "t_sec": t_s,
                "type": "mode",
                "label": f"Mode -> {mc.get('mode_name', 'Unknown')}",
                "severity": "warning" if mc.get("reason", 0) != 0 else "normal",
                "gps": get_gps_at(t_s),
            }
        )

    for msg in vibe_msgs:
        vibe_z = msg.get("VibeZ", 0)
        t_us = msg.get("TimeUS")
        if vibe_z > 30 and start_time is not None and t_us is not None:
            t_s = round((t_us - start_time) / 1e6, 2)
            timeline_events.append(
                {
                    "t_sec": t_s,
                    "type": "vibe_spike",
                    "label": f"Vibration Spike ({vibe_z:.1f} m/s^2)",
                    "severity": "warning",
                    "gps": get_gps_at(t_s),
                }
            )
            break

    timeline_events.append(
        {
            "t_sec": round(log_end_time_s, 2),
            "type": "crash",
            "label": "Log End / Impact",
            "severity": "crash",
            "gps": time_series["gps"][-1] if time_series["gps"] else None,
        }
    )
    timeline_events.sort(key=lambda event: event["t_sec"])

    return time_series, timeline_events


def _find_start_time_us(parsed: dict[str, Any]) -> int | None:
    message_groups = parsed.get("messages", {})
    for message_type in ("VIBE", "GPS"):
        for msg in message_groups.get(message_type, []):
            t_us = msg.get("TimeUS")
            if t_us is not None:
                return t_us

    for collection_name in ("errors", "mode_changes", "events"):
        for item in parsed.get(collection_name, []):
            t_us = item.get("time_us")
            if t_us is not None:
                return t_us

    return None


# ── Chat endpoint ─────────────────────────────────────────────────────────────
@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Answer questions about a log analysis using the rule-based AI assistant."""
    try:
        assistant = ChatAssistant()
        response_data = assistant.ask(request.question, request.analysis_result)
        return ChatResponse(
            question=response_data["question"],
            answer=response_data["answer"],
            confidence=response_data["confidence"],
            sources=response_data.get("sources", []),
            follow_up=response_data.get("follow_up", []),
        )
    except Exception:
        LOGGER.exception("Error during chat")
        return JSONResponse(
            status_code=500,
            content={"error": "Chat failed. Check server logs for details."},
        )


# ── Multi-flight comparison endpoint ─────────────────────────────────────────
@app.post("/api/compare", response_model=dict)
async def compare_flights(files: list[UploadFile] = File(...)):
    """Compare multiple flight logs for trend analysis and degradation detection."""
    if len(files) < 2:
        return JSONResponse(
            status_code=400,
            content={"error": "At least 2 files required for comparison"},
        )
    try:
        analysis_results = []

        for file in files:
            if not file.filename or not file.filename.lower().endswith(".bin"):
                continue

            fd, temp_path = tempfile.mkstemp(suffix=".bin")
            try:
                with os.fdopen(fd, "wb") as f:
                    content = await file.read()
                    f.write(content)

                result = await asyncio.to_thread(
                    _analyze_temp_log, temp_path, file.filename
                )
                analysis_results.append(result)
            finally:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass

        if len(analysis_results) < 2:
            return JSONResponse(
                status_code=400,
                content={"error": "Need at least 2 valid .BIN files"},
            )

        analyzer = TrendAnalyzer()
        trend_report = analyzer.compare_flights(analysis_results)
        return trend_report

    except Exception:
        LOGGER.exception("Error during comparison")
        return JSONResponse(
            status_code=500,
            content={"error": "Comparison failed. Check server logs for details."},
        )