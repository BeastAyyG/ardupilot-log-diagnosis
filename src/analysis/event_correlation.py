"""Deterministic event timeline and trigger/response correlation."""

from __future__ import annotations

from typing import Any


def build_event_timeline(parsed: dict[str, Any], window_sec: float = 2.0) -> dict[str, Any]:
    """Merge ERR/EV/MODE/MSG/PARM records into one deduplicated timeline."""

    records: list[dict[str, Any]] = []
    for item in parsed.get("errors", []) or []:
        records.append({"time_us": item.get("time_us"), "kind": "error", "name": item.get("subsystem_name", "ERR"), "detail": item})
    for item in parsed.get("events", []) or []:
        records.append({"time_us": item.get("time_us"), "kind": "event", "name": item.get("name", "EV"), "detail": item})
    for item in parsed.get("mode_changes", []) or []:
        records.append({"time_us": item.get("time_us"), "kind": "mode", "name": item.get("mode_name", "MODE"), "detail": item})
    for item in parsed.get("status_messages", []) or []:
        records.append({"time_us": item.get("time_us"), "kind": "status", "name": "MSG", "detail": item.get("message", "")})
    for item in parsed.get("parameter_changes", []) or []:
        records.append({"time_us": item.get("time_us"), "kind": "parameter", "name": item.get("name", "PARM"), "detail": item})
    records = [record for record in records if isinstance(record.get("time_us"), (int, float))]
    records.sort(key=lambda record: (float(record["time_us"]), record["kind"], record["name"]))
    timeline: list[dict[str, Any]] = []
    for record in records:
        if timeline and record["kind"] == timeline[-1]["kind"] and record["name"] == timeline[-1]["name"]:
            delta = float(record["time_us"]) - float(timeline[-1]["time_us"])
            if delta <= window_sec * 1e6:
                timeline[-1].setdefault("repeat_count", 1)
                timeline[-1]["repeat_count"] += 1
                timeline[-1]["last_time_us"] = int(record["time_us"])
                continue
        timeline.append({"time_us": int(record["time_us"]), "kind": record["kind"], "name": record["name"], "detail": record["detail"], "repeat_count": 1})

    edges: list[dict[str, Any]] = []
    for index, trigger in enumerate(timeline):
        if trigger["kind"] not in {"error", "event", "status", "parameter"}:
            continue
        for response in timeline[index + 1 :]:
            delta = float(response["time_us"]) - float(trigger["time_us"])
            if delta > window_sec * 1e6:
                break
            if response["kind"] in {"mode", "error", "event"} and response["name"] != trigger["name"]:
                edges.append({"from": trigger["name"], "to": response["name"], "delta_sec": round(delta / 1e6, 3), "relation": "nearby_response"})
                break
    nodes = [{"id": f"{item['kind']}:{item['name']}", "kind": item["kind"], "name": item["name"]} for item in timeline]
    return {
        "schema_version": "event-timeline.v1",
        "status": "reliable" if timeline else "insufficient_data",
        "window_sec": window_sec,
        "events": timeline,
        "causal_graph": {"nodes": nodes, "edges": edges, "method": "temporal-correlation-only"},
    }

