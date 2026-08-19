"""Offline GPX/KML track exports from parsed GPS telemetry.

The exporter intentionally does not reverse-geocode or upload coordinates.  A
caller can opt into exact coordinates; otherwise the report/privacy scrubber
should be used before sharing the resulting artifact.
"""

from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape
from typing import Any


def _points(source: dict[str, Any]) -> list[dict[str, float]]:
    if "messages" in source:
        values = source.get("messages", {}).get("GPS", [])
    else:
        values = source.get("gps_points", [])
    if not isinstance(values, list):
        return []
    result: list[dict[str, float]] = []
    for item in values:
        if not isinstance(item, dict):
            continue
        lat = item.get("Lat", item.get("lat", item.get("latitude")))
        lng = item.get("Lng", item.get("lng", item.get("lon", item.get("longitude"))))
        if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
            continue
        lat_value, lng_value = float(lat), float(lng)
        if abs(lat_value) > 90.0 or abs(lng_value) > 180.0:
            lat_value, lng_value = lat_value / 1e7, lng_value / 1e7
        if not (-90.0 <= lat_value <= 90.0 and -180.0 <= lng_value <= 180.0):
            continue
        point: dict[str, float] = {"lat": lat_value, "lng": lng_value}
        timestamp = item.get("TimeUS", item.get("time_us", item.get("timestamp_us")))
        altitude = item.get("Alt", item.get("alt", item.get("altitude")))
        if isinstance(timestamp, (int, float)):
            point["time_us"] = float(timestamp)
        if isinstance(altitude, (int, float)):
            point["alt"] = float(altitude)
        result.append(point)
    return result


def track_points(source: dict[str, Any]) -> dict[str, Any]:
    points = _points(source)
    return {"schema_version": "track-points.v1", "status": "reliable" if points else "insufficient_data", "point_count": len(points), "points": points}


def to_gpx(source: dict[str, Any], *, name: str = "ArduPilot flight") -> str:
    points = _points(source)
    rows = []
    for point in points:
        attributes = f'lat="{point["lat"]:.7f}" lon="{point["lng"]:.7f}"'
        elevation = f'<ele>{point["alt"]:.3f}</ele>' if "alt" in point else ""
        timestamp = f'<extensions><time_us>{point["time_us"]:.0f}</time_us></extensions>' if "time_us" in point else ""
        rows.append(f"<trkpt {attributes}>{elevation}{timestamp}</trkpt>")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + '<gpx version="1.1" creator="ArduPilot Log Diagnosis" xmlns="http://www.topografix.com/GPX/1/1">' + f"<trk><name>{escape(name)}</name><trkseg>{''.join(rows)}</trkseg></trk></gpx>"


def to_kml(source: dict[str, Any], *, name: str = "ArduPilot flight") -> str:
    points = _points(source)
    coordinates = " ".join(f"{point['lng']:.7f},{point['lat']:.7f},{point.get('alt', 0.0):.3f}" for point in points)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>' + f"<name>{escape(name)}</name><Placemark><name>{escape(name)}</name><LineString><altitudeMode>absolute</altitudeMode><coordinates>{coordinates}</coordinates></LineString></Placemark></Document></kml>"


def export_track(source: dict[str, Any], output_path: str | Path, *, format: str = "gpx", name: str = "ArduPilot flight") -> Path:
    format_name = format.lower().lstrip(".")
    if format_name not in {"gpx", "kml"}:
        raise ValueError("Track format must be gpx or kml")
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    content = to_gpx(source, name=name) if format_name == "gpx" else to_kml(source, name=name)
    destination.write_text(content, encoding="utf-8")
    return destination
