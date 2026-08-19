"""Local, side-effect-free fleet alert evaluation.

The analyzer returns which rules would fire.  Sending a webhook remains an
operator-owned integration and is deliberately outside this package.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


def validate_webhook_url(url: str) -> dict[str, Any]:
    parsed = urlparse(str(url).strip())
    host = (parsed.hostname or "").lower()
    valid = parsed.scheme == "https" and bool(host) and host not in {"localhost", "127.0.0.1", "::1"} and not host.endswith(".local")
    return {"valid": valid, "scheme": parsed.scheme, "host": host or None, "reason": "https-only public webhook URL" if valid else "Only an https URL with a non-local hostname is accepted."}


def evaluate_alerts(report: dict[str, Any], rules: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    score = (report.get("health_score", {}) or {}).get("score")
    hardware = report.get("hardware_report", {}) or {}
    findings = report.get("diagnoses", []) or []
    rules = rules or []
    fired: list[dict[str, Any]] = []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        rule_id = str(rule.get("id", "unnamed"))
        threshold = rule.get("below")
        if rule.get("metric") == "health_score" and isinstance(score, (int, float)) and isinstance(threshold, (int, float)) and float(score) < float(threshold):
            fired.append({"id": rule_id, "reason": f"health score {score} is below {threshold}", "severity": rule.get("severity", "warning")})
        if rule.get("metric") == "diagnosis_severity":
            wanted = str(rule.get("value", "critical")).lower()
            matches = [item.get("failure_type", "unknown") for item in findings if str(item.get("severity", "")).lower() == wanted]
            if matches:
                fired.append({"id": rule_id, "reason": f"{len(matches)} {wanted} finding(s): {', '.join(map(str, matches[:3]))}", "severity": rule.get("severity", wanted)})
        if rule.get("metric") == "battery_sag" and isinstance(rule.get("above"), (int, float)):
            sag = ((hardware.get("sensor_metrics", {}) or {}).get("battery", {}) or {}).get("voltage_sag")
            if isinstance(sag, (int, float)) and float(sag) > float(rule["above"]):
                fired.append({"id": rule_id, "reason": f"battery sag {sag} is above {rule['above']}", "severity": rule.get("severity", "warning")})
    return {"schema_version": "fleet-alert-preview.v1", "status": "alert" if fired else "clear", "fired": fired, "evaluated_rule_count": len(rules), "network_action": "none; this endpoint only previews alerts"}
