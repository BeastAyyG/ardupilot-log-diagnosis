from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from src.diagnosis.decision_policy import evaluate_decision
from src.diagnosis.hybrid_engine import HybridEngine
from src.diagnosis.rule_engine import RuleEngine
from src.features.pipeline import FeaturePipeline
from src.parser.bin_parser import LogParser


LOGGER = logging.getLogger(__name__)
MAX_UPLOAD_BYTES = 64 * 1024 * 1024
UPLOAD_CHUNK_SIZE = 1024 * 1024
WEB_DIR = Path(__file__).parent.absolute()

app = FastAPI(title="ArduPilot Log Diagnosis API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_class=HTMLResponse)
async def get_index() -> str:
    index_path = WEB_DIR / "index.html"
    if index_path.exists():
        return index_path.read_text(encoding="utf-8")
    return "UI not found"


@app.post("/api/analyze")
async def analyze_log(file: UploadFile = File(...)) -> JSONResponse:
    if not file.filename or not file.filename.lower().endswith(".bin"):
        return JSONResponse(status_code=400, content={"error": "Only .BIN files are supported."})

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
                        content={"error": f"Uploaded file exceeds {MAX_UPLOAD_BYTES} bytes."},
                    )
                handle.write(chunk)

        result = await asyncio.to_thread(_analyze_temp_log, temp_path, file.filename)
        return JSONResponse(content=result)
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
