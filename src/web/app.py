import os
import json
import logging
import tempfile
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

from src.parser.bin_parser import LogParser
from src.features.pipeline import FeaturePipeline
from src.diagnosis.hybrid_engine import HybridEngine

app = FastAPI(title="ArduPilot Log Diagnosis API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = HybridEngine()

WEB_DIR = Path(__file__).parent.absolute()

@app.get("/", response_class=HTMLResponse)
async def get_index():
    index_path = WEB_DIR / "index.html"
    if index_path.exists():
        return index_path.read_text(encoding="utf-8")
    return "UI not found"

@app.post("/api/analyze")
async def analyze_log(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".bin"):
        return JSONResponse(status_code=400, content={"error": "Only .BIN files are supported."})

    fd, temp_path = tempfile.mkstemp(suffix=".bin")
    try:
        with os.fdopen(fd, 'wb') as f:
            content = await file.read()
            f.write(content)
        
        parser = LogParser(temp_path)
        parsed = parser.parse()
        
        pipeline = FeaturePipeline()
        features = pipeline.extract(parsed)
        
        diagnoses, explain_data = engine.diagnose(features)
        
        # --- EXTRACT JAW-DROPPING TIME SERIES DATA ---
        time_series = {"gps": [], "vibe": []}
        start_time = None
        
        # Determine log start/end time from VIBE messages
        vibe_msgs = parsed.get("messages", {}).get("VIBE", [])
        if vibe_msgs:
            raw_times = [m.get("TimeUS") for m in vibe_msgs if m.get("TimeUS")]
            if raw_times:
                start_time = raw_times[0]
                log_end_time_s = (raw_times[-1] - start_time) / 1e6
            else:
                log_end_time_s = features.get("_metadata", {}).get("duration_sec", 0)
        else:
            log_end_time_s = features.get("_metadata", {}).get("duration_sec", 0)

        # Downsample VIBE for Interactive Plot
        step = max(1, len(vibe_msgs) // 500)
        for msg in vibe_msgs[::step]:
            t = msg.get("TimeUS")
            if t is None: continue
            if start_time is None: start_time = t
            time_series["vibe"].append({
                "t": round((t - start_time) / 1e6, 2),
                "x": msg.get("VibeX", 0),
                "y": msg.get("VibeY", 0),
                "z": msg.get("VibeZ", 0)
            })

        # Extract GPS for 3D Flight Path Rendering
        gps_msgs = parsed.get("messages", {}).get("GPS", [])
        step_gps = max(1, len(gps_msgs) // 500)
        for msg in gps_msgs[::step_gps]:
            lat = msg.get("Lat")
            lng = msg.get("Lng")
            alt = msg.get("Alt", 0)
            if lat and lng and lat != 0 and lng != 0:
                time_series["gps"].append({
                    "lat": lat / 1e7,
                    "lng": lng / 1e7,
                    "alt": alt
                })

        # --- CRASH CAUSALITY TIMELINE ----------------------------------------
        # Build a sequence of annotated events sorted by time so the UI
        # can render a colour-coded swimlane. Each event has:
        #   t_sec   : seconds from log start
        #   type    : "error" | "mode" | "vibe_spike" | "crash"
        #   label   : human-readable name
        #   severity: "normal" | "warning" | "critical" | "crash"
        timeline_events = []

        # 1. ERR messages → real hardware / EKF errors
        ERR_LABEL_MAP = {
            3:  ("Compass Error",       "critical"),
            5:  ("Radio Failsafe",      "critical"),
            6:  ("Battery Failsafe",    "critical"),
            11: ("GPS Glitch",          "warning"),
            12: ("Crash Detected",      "crash"),
            16: ("EKF Check Failed",    "critical"),
            17: ("EKF Failsafe",        "crash"),
            25: ("Thrust Loss",         "critical"),
            29: ("Vibration Failsafe",  "critical"),
        }
        for err in parsed.get("errors", []):
            t_us = err.get("time_us")
            if t_us is None or start_time is None: continue
            t_s = round((t_us - start_time) / 1e6, 2)
            subsys = err.get("subsystem", 0)
            label, sev = ERR_LABEL_MAP.get(subsys, (err.get("subsystem_name", "Error"), "warning"))
            timeline_events.append({"t_sec": t_s, "type": "error", "label": label, "severity": sev})

        # 2. MODE changes — show pilot actions / failsafe-induced mode flips
        for mc in parsed.get("mode_changes", []):
            t_us = mc.get("time_us")
            if t_us is None or start_time is None: continue
            t_s = round((t_us - start_time) / 1e6, 2)
            timeline_events.append({
                "t_sec": t_s,
                "type": "mode",
                "label": f"Mode → {mc.get('mode_name', 'Unknown')}",
                "severity": "warning" if mc.get("reason", 0) != 0 else "normal"
            })

        # 3. Vibration spike — find first time VIBE.VibeZ > 30 m/s² (danger zone)
        vibe_spike_found = False
        for msg in vibe_msgs:
            if msg.get("VibeZ", 0) > 30 and start_time:
                t_s = round((msg["TimeUS"] - start_time) / 1e6, 2)
                timeline_events.append({
                    "t_sec": t_s,
                    "type": "vibe_spike",
                    "label": f"Vibration Spike (VibeZ={msg['VibeZ']:.1f} m/s²)",
                    "severity": "warning"
                })
                vibe_spike_found = True
                break

        # 4. Log end = crash point (log cuts out at impact)
        timeline_events.append({
            "t_sec": round(log_end_time_s, 2),
            "type": "crash",
            "label": "Log End / Impact",
            "severity": "crash"
        })

        timeline_events.sort(key=lambda e: e["t_sec"])

        result = {
            "metadata": {
                "filename": file.filename,
                "duration": features.get("_metadata", {}).get("duration_sec", 0),
                "vehicle": features.get("_metadata", {}).get("vehicle_type", "Unknown")
            },
            "features": features,
            "diagnoses": diagnoses,
            "explain_data": explain_data,
            "time_series": time_series,
            "timeline_events": timeline_events
        }
        return JSONResponse(content=result)
    except Exception as e:
        logging.exception("Error during analysis")
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
