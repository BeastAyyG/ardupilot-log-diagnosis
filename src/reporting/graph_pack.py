"""Offline, self-contained interactive graph-pack exports.

The upstream agent workflow calls these "Plotly graph packs".  This project
keeps the same useful property—one portable HTML artifact with embedded data—
without loading a remote JavaScript bundle or sending telemetry anywhere.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.reporting.geo_export import track_points


def _numeric_series(report: dict[str, Any]) -> list[dict[str, Any]]:
    features = report.get("features_summary", report.get("features", {})) or {}
    return [{"name": str(key), "values": [float(value)]} for key, value in list(features.items())[:40] if isinstance(value, (int, float))]


def _payload(report: dict[str, Any], parsed: dict[str, Any] | None = None) -> dict[str, Any]:
    source = parsed if isinstance(parsed, dict) else {}
    track = track_points(source) if source else {"status": "insufficient_data", "points": [], "point_count": 0}
    points = track.get("points", [])
    latitudes = [float(item["lat"]) for item in points if isinstance(item, dict) and isinstance(item.get("lat"), (int, float))]
    longitudes = [float(item["lng"]) for item in points if isinstance(item, dict) and isinstance(item.get("lng"), (int, float))]
    altitudes = [float(item["alt"]) for item in points if isinstance(item, dict) and isinstance(item.get("alt"), (int, float))]
    track_summary = {
        "point_count": len(points),
        "bounds": {"lat": [min(latitudes), max(latitudes)], "lng": [min(longitudes), max(longitudes)]} if latitudes and longitudes else None,
        "altitude_m": {"min": min(altitudes), "max": max(altitudes)} if altitudes else None,
    }
    return {
        "schema_version": "graph-pack-data.v1",
        "diagnoses": [
            {"failure_type": item.get("failure_type", "unknown"), "confidence": item.get("confidence", 0.0), "severity": item.get("severity", "info")}
            for item in (report.get("diagnoses", []) or []) if isinstance(item, dict)
        ],
        "health_score": report.get("health_score", {}),
        "features": _numeric_series(report),
        "track": points,
        "track_summary": track_summary,
    }


def _html(data: dict[str, Any], title: str) -> str:
    serialized = json.dumps(data, separators=(",", ":"), ensure_ascii=True).replace("</", "<\\/")
    safe_title = str(title).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f'''<!doctype html>
<html><head><meta charset="utf-8"><title>{safe_title}</title>
<style>body{{font:14px system-ui;background:#101522;color:#e8edf7;margin:24px}}h1{{font-size:22px}}.card{{background:#182236;border:1px solid #2a3b5e;border-radius:8px;padding:14px;margin:12px 0}}svg{{width:100%;height:280px;background:#0d1320;border-radius:6px}}.muted{{color:#9aaccc}}</style></head>
<body><h1>{safe_title}</h1><p class="muted">Offline graph pack; no network requests and no vehicle writes.</p>
<div class="card"><strong>Health:</strong> <span id="health">—</span> / 100</div>
<div class="card"><strong>Diagnoses</strong><ul id="diagnoses"></ul></div>
<div class="card"><strong>Feature summary</strong><svg id="bars" viewBox="0 0 900 280" role="img" aria-label="Feature summary"></svg></div>
<div class="card"><strong>Track samples:</strong> <span id="track">0</span><svg id="track_view" viewBox="0 0 900 320" role="img" aria-label="Flight trajectory"></svg></div>
<div class="card"><strong>Altitude profile</strong><svg id="altitude_view" viewBox="0 0 900 220" role="img" aria-label="Altitude profile"></svg></div>
<script>
const data={serialized};
const score=(data.health_score||{{}}).score;
document.getElementById('health').textContent=score ?? 'n/a';
const list=document.getElementById('diagnoses');
(data.diagnoses||[]).forEach(d=>{{const li=document.createElement('li');li.textContent=`${{d.failure_type}} — ${{Math.round((d.confidence||0)*100)}}% (${{d.severity}})`;list.appendChild(li);}});
document.getElementById('track').textContent=(data.track||[]).length;
const ns='http://www.w3.org/2000/svg';
const trackSvg=document.getElementById('track_view');
const trackPoints=(data.track||[]).filter(p=>Number.isFinite(Number(p.lat))&&Number.isFinite(Number(p.lng)));
if(trackPoints.length>1){{
  const lats=trackPoints.map(p=>Number(p.lat)), lngs=trackPoints.map(p=>Number(p.lng));
  const minLat=Math.min(...lats), maxLat=Math.max(...lats), minLng=Math.min(...lngs), maxLng=Math.max(...lngs);
  const latSpan=Math.max(maxLat-minLat,1e-9), lngSpan=Math.max(maxLng-minLng,1e-9);
  const coords=trackPoints.map(p=>`${{20+(Number(p.lng)-minLng)/lngSpan*860}},${{300-(Number(p.lat)-minLat)/latSpan*280}}`).join(' ');
  const path=document.createElementNS(ns,'polyline');path.setAttribute('points',coords);path.setAttribute('fill','none');path.setAttribute('stroke','#50d890');path.setAttribute('stroke-width','3');trackSvg.appendChild(path);
  const start=document.createElementNS(ns,'circle');start.setAttribute('cx',20+(Number(trackPoints[0].lng)-minLng)/lngSpan*860);start.setAttribute('cy',300-(Number(trackPoints[0].lat)-minLat)/latSpan*280);start.setAttribute('r','6');start.setAttribute('fill','#3fa7ff');trackSvg.appendChild(start);
  const lastPoint=trackPoints[trackPoints.length-1];
  const end=document.createElementNS(ns,'circle');end.setAttribute('cx',20+(Number(lastPoint.lng)-minLng)/lngSpan*860);end.setAttribute('cy',300-(Number(lastPoint.lat)-minLat)/latSpan*280);end.setAttribute('r','6');end.setAttribute('fill','#ff9f43');trackSvg.appendChild(end);
}} else {{trackSvg.innerHTML='<text x="20" y="40" fill="#9aaccc">No GPS trajectory available</text>';}}
const altitudeSvg=document.getElementById('altitude_view');
const altitudePoints=(data.track||[]).filter(p=>Number.isFinite(Number(p.alt))&&Number.isFinite(Number(p.time_us)));
if(altitudePoints.length>1){{
  const altitudes=altitudePoints.map(p=>Number(p.alt));
  const minAlt=Math.min(...altitudes), maxAlt=Math.max(...altitudes), altSpan=Math.max(maxAlt-minAlt,1e-9);
  const firstTime=Number(altitudePoints[0].time_us), lastTime=Number(altitudePoints[altitudePoints.length-1].time_us), timeSpan=Math.max(lastTime-firstTime,1);
  const coords=altitudePoints.map(p=>`${{20+(Number(p.time_us)-firstTime)/timeSpan*860}},${{200-(Number(p.alt)-minAlt)/altSpan*180}}`).join(' ');
  const path=document.createElementNS(ns,'polyline');path.setAttribute('points',coords);path.setAttribute('fill','none');path.setAttribute('stroke','#ff9f43');path.setAttribute('stroke-width','3');altitudeSvg.appendChild(path);
  const label=document.createElementNS(ns,'text');label.setAttribute('x','20');label.setAttribute('y','18');label.setAttribute('fill','#9aaccc');label.textContent=`${{minAlt.toFixed(1)}}–${{maxAlt.toFixed(1)}} m`;altitudeSvg.appendChild(label);
}} else {{altitudeSvg.innerHTML='<text x="20" y="40" fill="#9aaccc">No altitude profile available</text>';}}
const svg=document.getElementById('bars');
(data.features||[]).slice(0,12).forEach((item,i)=>{{const value=Math.abs(Number(item.values[0]||0));const h=Math.min(220,Math.log10(1+value)*45+8);const x=12+i*72;const rect=document.createElementNS(ns,'rect');rect.setAttribute('x',x);rect.setAttribute('y',250-h);rect.setAttribute('width',52);rect.setAttribute('height',h);rect.setAttribute('fill','#3fa7ff');svg.appendChild(rect);const text=document.createElementNS(ns,'text');text.setAttribute('x',x+2);text.setAttribute('y',270);text.setAttribute('fill','#b8c9e8');text.setAttribute('font-size','9');text.textContent=item.name.slice(0,10);svg.appendChild(text);}});
</script></body></html>'''


def generate_graph_pack(report: dict[str, Any], *, parsed: dict[str, Any] | None = None, title: str = "ArduPilot flight graph pack") -> dict[str, Any]:
    data = _payload(report, parsed)
    html = _html(data, title)
    return {"schema_version": "graph-pack.v1", "status": "reliable", "title": title, "mime_type": "text/html", "html": html, "data": data, "network_requests": 0, "write_parameters": False}


def export_graph_pack(report: dict[str, Any], output_path: str | Path, *, parsed: dict[str, Any] | None = None, title: str = "ArduPilot flight graph pack") -> Path:
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(generate_graph_pack(report, parsed=parsed, title=title)["html"], encoding="utf-8")
    return destination
