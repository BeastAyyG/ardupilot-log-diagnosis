"""Offline mission/waypoint and operator-supplied geofence checks."""

from __future__ import annotations

import math
from typing import Any



def _track_points(parsed: dict[str, Any]) -> list[dict[str, float]]:
    values = (parsed.get("messages", {}) or {}).get("GPS", [])
    if not isinstance(values, list):
        return []
    points: list[dict[str, float]] = []
    for item in values:
        if not isinstance(item, dict):
            continue
        lat = item.get("Lat", item.get("lat", item.get("latitude")))
        lng = item.get("Lng", item.get("lng", item.get("longitude", item.get("lon"))))
        if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
            continue
        lat_value, lng_value = float(lat), float(lng)
        if not math.isfinite(lat_value) or not math.isfinite(lng_value):
            continue
        if abs(lat_value) > 90.0 or abs(lng_value) > 180.0:
            lat_value, lng_value = lat_value / 1e7, lng_value / 1e7
        if -90.0 <= lat_value <= 90.0 and -180.0 <= lng_value <= 180.0:
            points.append({"lat": lat_value, "lng": lng_value})
    return points


def _coordinate(value: Any, scale: float = 1.0) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    result = float(value) / scale
    return result if math.isfinite(result) else None


def normalize_mission(mission: Any) -> list[dict[str, Any]]:
    if isinstance(mission, str):
        rows: list[dict[str, Any]] = []
        for line in mission.splitlines():
            fields = [field.strip() for field in line.split("\t")]
            if len(fields) < 12 or not fields[0].isdigit():
                continue
            try:
                latitude, longitude, altitude = float(fields[8]), float(fields[9]), float(fields[10])
            except (TypeError, ValueError):
                continue
            rows.append({"seq": int(fields[0]), "command": int(fields[3]) if fields[3].isdigit() else fields[3], "lat": latitude, "lng": longitude, "alt": altitude})
        return rows
    if not isinstance(mission, list):
        return []
    result = []
    for index, item in enumerate(mission):
        if not isinstance(item, dict):
            continue
        lat_raw = item.get("lat", item.get("latitude", item.get("Lat")))
        # Use the selected alias when deciding whether the value is a
        # DataFlash 1e-7-degree integer.  The previous expression inspected
        # only ``lat`` and therefore rejected valid ``latitude``/``Lat``
        # mission payloads that used scaled coordinates.
        lat = _coordinate(lat_raw, 1e7 if isinstance(lat_raw, (int, float)) and abs(float(lat_raw)) > 90 else 1.0) if isinstance(lat_raw, (int, float)) else None
        lng_raw = item.get("lng", item.get("longitude", item.get("Lng")))
        lng = _coordinate(lng_raw, 1e7 if isinstance(lng_raw, (int, float)) and abs(float(lng_raw)) > 180 else 1.0)
        if lat is None or lng is None:
            continue
        altitude = item.get("alt", item.get("altitude", item.get("Alt")))
        if isinstance(altitude, (int, float)) and math.isfinite(float(altitude)):
            altitude = float(altitude)
        result.append({"seq": item.get("seq", item.get("sequence", index)), "command": item.get("command", item.get("Command")), "lat": lat, "lng": lng, "alt": altitude})
    return result


def validate_mission(mission: Any, *, geofence: list[dict[str, float]] | None = None, rally_points: Any = None) -> dict[str, Any]:
    waypoints = normalize_mission(mission)
    issues: list[dict[str, Any]] = []
    seen: set[Any] = set()
    for item in waypoints:
        if item["seq"] in seen:
            issues.append({"type": "duplicate_sequence", "seq": item["seq"]})
        seen.add(item["seq"])
        if not (-90 <= item["lat"] <= 90 and -180 <= item["lng"] <= 180):
            issues.append({"type": "invalid_coordinate", "seq": item["seq"]})
        if item.get("alt") is None:
            issues.append({"type": "missing_altitude", "seq": item["seq"]})
        elif not isinstance(item.get("alt"), (int, float)):
            issues.append({"type": "invalid_altitude", "seq": item["seq"]})
    fence = normalize_mission(geofence or [])
    rally = normalize_mission(rally_points or [])
    fence_issues = []
    if geofence and len(fence) < 3:
        fence_issues.append({"type": "invalid_geofence", "reason": "A polygon geofence requires at least three valid points."})
    issues.extend(fence_issues)
    status = "reliable" if waypoints and not issues else "review" if waypoints else "insufficient_data"
    return {"schema_version": "mission-plan.v1", "status": status, "waypoint_count": len(waypoints), "waypoints": waypoints, "issues": issues, "geofence": {"point_count": len(fence), "provided": bool(fence), "issues": fence_issues}, "rally_points": {"count": len(rally), "provided": bool(rally)}, "write_parameters": False}


def _distance_m(a: dict[str, float], b: dict[str, float]) -> float:
    lat_scale = 111_320.0
    lng_scale = lat_scale * math.cos(math.radians((a["lat"] + b["lat"]) / 2.0))
    return math.hypot((a["lat"] - b["lat"]) * lat_scale, (a["lng"] - b["lng"]) * lng_scale)


def _inside_polygon(point: dict[str, float], polygon: list[dict[str, float]]) -> bool:
    inside = False
    for left, right in zip(polygon, polygon[1:] + polygon[:1]):
        crosses = (left["lng"] > point["lng"]) != (right["lng"] > point["lng"])
        if crosses:
            delta_lng = right["lng"] - left["lng"]
            # Preserve the sign of the longitude span.  Using ``max`` here
            # changed every westward edge to a tiny positive denominator and
            # produced incorrect fence results for clockwise polygons.
            if abs(delta_lng) <= 1e-12:
                continue
            edge_lat = (right["lat"] - left["lat"]) * (point["lng"] - left["lng"]) / delta_lng + left["lat"]
            if point["lat"] < edge_lat:
                inside = not inside
    return inside


def mission_compliance_report(parsed: dict[str, Any], mission: Any, *, tolerance_m: float = 30.0, geofence: list[dict[str, float]] | None = None) -> dict[str, Any]:
    tolerance_m = max(0.1, min(float(tolerance_m), 10_000.0))
    plan = validate_mission(mission, geofence=geofence)
    points = _track_points(parsed)
    if not plan["waypoints"] or not points:
        return {"schema_version": "mission-compliance.v2", "status": "insufficient_data", "plan": plan, "waypoints": [], "observed_points": len(points), "write_parameters": False}
    observed: list[dict[str, Any]] = []
    cursor = 0
    for waypoint in plan["waypoints"]:
        best_index, best_distance = None, float("inf")
        for index in range(cursor, len(points)):
            distance = _distance_m(waypoint, points[index])
            if distance < best_distance:
                best_index, best_distance = index, distance
        hit = best_index is not None and best_distance <= tolerance_m
        observed.append({"seq": waypoint["seq"], "command": waypoint.get("command"), "status": "hit" if hit else "missed_or_out_of_tolerance", "nearest_distance_m": round(best_distance, 2) if best_index is not None else None, "nearest_index": best_index})
        if best_index is not None:
            cursor = best_index
    fence = normalize_mission(geofence or [])
    fence_violations = [point for point in points if len(fence) >= 3 and not _inside_polygon(point, fence)]
    return {"schema_version": "mission-compliance.v2", "status": "review_only", "plan": plan, "waypoints": observed, "observed_points": len(points), "hit_count": sum(item["status"] == "hit" for item in observed), "fence_violation_count": len(fence_violations), "tolerance_m": tolerance_m, "warning": "Interpret deviations with vehicle profile, mission timing, and GPS quality; this is not a flight-safety certification.", "write_parameters": False}
