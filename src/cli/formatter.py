import json
import os
import sys
from typing import Optional

from src.contracts import DecisionDict, DiagnosisDict, FeatureDict, FeatureMetadata


def _use_color() -> bool:
    return sys.stdout.isatty() and os.environ.get("NO_COLOR", "") == ""


_RESET = "\033[0m"
_BOLD = "\033[1m"
_RED = "\033[91m"
_YELLOW = "\033[93m"
_GREEN = "\033[92m"
_CYAN = "\033[96m"
_DIM = "\033[2m"


def _c(text: str, *codes: str) -> str:
    if not _use_color():
        return text
    return "".join(codes) + text + _RESET


def _format_onset_time(tanomaly: object, metadata: FeatureMetadata) -> str:
    if not isinstance(tanomaly, (int, float)) or tanomaly <= 0:
        return "no onset timestamp"

    origin_us = metadata.get("first_time_us", 0)
    relative_us = float(tanomaly)
    if isinstance(origin_us, (int, float)) and origin_us > 0 and tanomaly >= origin_us:
        relative_us -= float(origin_us)
    return f"T+{relative_us / 1e6:.1f}s"


_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>ArduPilot Log Diagnosis - {filename}</title>
<style>
  body{{font-family:system-ui,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem;color:#1a1a2e;background:#f4f6f9}}
  h1{{font-size:1.4rem;margin-bottom:.25rem}}
  .meta{{color:#555;font-size:.85rem;margin-bottom:1.5rem}}
  .badge{{display:inline-block;padding:.25rem .7rem;border-radius:999px;font-weight:700;font-size:.8rem;margin-right:.4rem}}
  .critical{{background:#fde8e8;color:#c0392b}}
  .warning{{background:#fef9e7;color:#d35400}}
  .info{{background:#e8f6fd;color:#2471a3}}
  .healthy{{background:#e9f7ef;color:#1e8449}}
  .card{{background:#fff;border-radius:8px;box-shadow:0 1px 4px rgba(0,0,0,.1);padding:1.2rem 1.5rem;margin-bottom:1rem}}
  .card h2{{margin:0 0 .5rem;font-size:1rem}}
  .evidence{{background:#f8f9fa;border-left:3px solid #aaa;padding:.4rem .8rem;margin:.5rem 0;font-family:monospace;font-size:.85rem}}
  .fix{{margin-top:.5rem;font-size:.9rem;color:#333}}
  .subsystem-table{{width:100%;border-collapse:collapse;font-size:.88rem}}
  .subsystem-table td,.subsystem-table th{{padding:.35rem .6rem;border-bottom:1px solid #eee;text-align:left}}
  .bar{{display:inline-block;height:10px;border-radius:3px;background:#3498db;vertical-align:middle}}
  .similar-case,.hypothesis,.warning-box{{border-left:3px solid #3498db;padding:.4rem .8rem;margin:.4rem 0;font-size:.88rem}}
  .warning-box{{border-left-color:#d35400;background:#fffaf0}}
</style>
</head>
<body>
<h1>ArduPilot Log Diagnosis Report</h1>
<div class="meta">
  <strong>Log:</strong> {filename} &nbsp;·&nbsp;
  <strong>Duration:</strong> {duration} &nbsp;·&nbsp;
  <strong>Vehicle:</strong> {vehicle}
</div>
{body}
</body>
</html>
"""


class DiagnosisFormatter:
    def format_terminal(
        self,
        diagnoses: list[DiagnosisDict],
        metadata: FeatureMetadata,
        decision: Optional[DecisionDict] = None,
        similar_cases: Optional[list] = None,
        runtime_info: Optional[dict] = None,
        parameter_warnings: Optional[list[dict]] = None,
        explain_data: Optional[dict] = None,
    ) -> str:
        filename = metadata.get("log_file", "unknown").split("/")[-1]
        duration = metadata.get("duration_sec", 0.0)
        mins = int(duration // 60)
        secs = int(duration % 60)
        vehicle = f"{metadata.get('vehicle_type', 'Unknown')} {metadata.get('firmware', '')}".strip()

        lines = [
            _c("ArduPilot Log Diagnosis Report", _BOLD),
            f"Log: {filename}",
            f"Duration: {mins}m {secs}s",
            f"Vehicle: {vehicle}",
            "",
        ]

        quality_report = metadata.get("quality_report", {})
        if quality_report and isinstance(quality_report, dict) and quality_report.get("overall_status") != "UNKNOWN":
            overall_status = quality_report.get("overall_status", "RELIABLE")
            q_color = _GREEN if overall_status == "RELIABLE" else (_YELLOW if overall_status == "DEGRADED" else _RED)
            lines.append(_c(f"Log Quality & Capability Check: {overall_status}", q_color, _BOLD))
            for cap_name, cap_info in quality_report.get("capabilities", {}).items():
                if isinstance(cap_info, dict) and cap_info.get("status") in ("DEGRADED", "UNSUPPORTED"):
                    c_status = cap_info.get("status", "")
                    c_color = _YELLOW if c_status == "DEGRADED" else _RED
                    lines.append(f"  [{_c(c_status, c_color)}] {cap_name}: {cap_info.get('reason')}")
                    if cap_info.get("recommendation"):
                        lines.append(_c(f"     -> Recommendation: {cap_info.get('recommendation')}", _CYAN))
            lines.append("")

        if parameter_warnings:
            lines.append(_c("Pre-Flight & Parameter Validation", _YELLOW, _BOLD))
            for item in parameter_warnings:
                lines.append(f"  - {item['message']}")
            lines.append("")

        if not diagnoses:
            decision_status = (decision or {}).get(
                "status",
                "no_fault_detected",
            )
            if decision_status == "insufficient_data":
                lines.append(
                    _c(
                        "INSUFFICIENT DATA - The available telemetry cannot "
                        "support a reliable diagnosis.",
                        _RED,
                        _BOLD,
                    )
                )
            elif decision_status == "uncertain":
                lines.append(
                    _c(
                        "UNCERTAIN - No fault crossed the threshold, but log "
                        "capabilities are degraded.",
                        _YELLOW,
                        _BOLD,
                    )
                )
            else:
                lines.append(
                    _c(
                        "NO FAULT DETECTED - Supported checks found no reportable "
                        "fault. This is not a safe-to-fly certification.",
                        _GREEN,
                        _BOLD,
                    )
                )
        else:
            for diag in diagnoses:
                pct = int(diag["confidence"] * 100)
                severity = diag["severity"].upper()
                color = _RED if severity == "CRITICAL" else (_YELLOW if severity == "WARNING" else _CYAN)
                lines.append(
                    _c(
                        f"{severity} - {diag['failure_type'].upper()} ({pct}%)",
                        color,
                        _BOLD,
                    )
                )
                for ev in diag.get("evidence", []):
                    lines.append(
                        _c(
                            f"  {ev.get('feature')} = {ev.get('value')} "
                            f"(limit: {ev.get('threshold')})",
                            _DIM,
                        )
                    )
                lines.append(f"  Method: {diag['detection_method']}")
                lines.append(_c(f"  Fix: {diag['recommendation']}", _CYAN))
                lines.append("")

        hypotheses = (explain_data or {}).get("hypotheses", [])
        arbiter = (explain_data or {}).get("causal_arbiter", {})
        temporal_evidence = [
            item
            for item in (explain_data or {}).get("temporal_evidence", [])
            if item.get("status") == "satisfied"
        ]
        if temporal_evidence:
            lines.append(_c("Temporal Logic Evidence", _BOLD))
            for item in temporal_evidence:
                lines.append(
                    f"  [{item['rule_id']}] {item['explanation']}"
                )
            lines.append("")
        matrix_profile = (explain_data or {}).get("matrix_profile", {})
        if matrix_profile.get("status") == "candidate":
            channels = ", ".join(
                str(item["channel"])
                for item in matrix_profile.get("contributing_channels", [])[:3]
            )
            lines.append(_c("Label-Free Temporal Discord", _BOLD))
            lines.append(
                "  Candidate window: "
                f"T+{float(matrix_profile.get('onset_sec', 0.0)):.1f}s "
                f"(score={float(matrix_profile.get('score', 0.0)):.3f})"
            )
            if channels:
                lines.append(f"  Leading channels: {channels}")
            lines.append(
                "  This is an anomaly candidate, not a failure label."
            )
            lines.append("")
        if hypotheses:
            lines.append(_c("Hypothesis Scaffolding", _BOLD))
            for idx, item in enumerate(hypotheses[:3], start=1):
                tanomaly = item.get("tanomaly", -1.0)
                time_text = _format_onset_time(tanomaly, metadata)
                lines.append(
                    f"  Hypothesis {idx}: {item['failure_type']} "
                    f"({item['merged_confidence'] * 100:.0f}%) via {item['source']} "
                    f"from {item.get('lead_feature') or 'telemetry correlation'} at {time_text}."
                )
            if arbiter:
                lines.append(f"  Causal Arbiter: {arbiter.get('reason', 'no arbiter summary')}")
            lines.append("")

        if decision:
            lines.append(f"Decision: {decision.get('status', 'unknown').upper()}")
            top_guess = decision.get("top_guess")
            if top_guess:
                selected_by_arbiter = (
                    (explain_data or {})
                    .get("causal_arbiter", {})
                    .get("selected_failure_type")
                    == top_guess
                )
                guess_label = "Likely Root Cause" if selected_by_arbiter else "Top Guess"
                lines.append(
                    f"{guess_label}: {top_guess.upper()} "
                    f"({int(float(decision.get('top_confidence', 0.0)) * 100)}%)"
                )
                strongest = max(
                    diagnoses,
                    key=lambda item: float(item.get("confidence", 0.0)),
                    default=None,
                )
                if (
                    strongest
                    and strongest.get("failure_type") != top_guess
                    and float(strongest.get("confidence", 0.0))
                    > float(decision.get("top_confidence", 0.0))
                ):
                    lines.append(
                        "Highest-Confidence Finding: "
                        f"{str(strongest['failure_type']).upper()} "
                        f"({int(float(strongest['confidence']) * 100)}%)"
                    )
            subsystems = decision.get("ranked_subsystems", [])
            if subsystems:
                lines.append("Subsystem Blame Ranking:")
                for item in subsystems[:3]:
                    lines.append(f"  - {item['subsystem']}: {int(item['likelihood'] * 100)}%")
            if decision.get("requires_human_review"):
                lines.append(_c("Human Review: REQUIRED", _YELLOW, _BOLD))
                for rationale in decision.get("rationale", []):
                    lines.append(f"  - {rationale}")
            capability = decision.get("applicable_capability")
            if capability:
                lines.append(
                    "Capability Gate: "
                    f"{capability} [{decision.get('capability_status', 'UNKNOWN')}]"
                )

        if runtime_info:
            lines.append("")
            lines.append(f"Runtime: {runtime_info.get('engine', 'unknown')}")
            if runtime_info.get("ml_available") is False:
                lines.append(f"ML Status: fallback ({runtime_info.get('ml_reason', 'ml unavailable')})")
            elif runtime_info.get("ml_confirmation_allowed") is False:
                lines.append(
                    "ML Status: advisory only "
                    f"({runtime_info.get('ml_risk_status', 'risk gate not passed')})"
                )

        if similar_cases:
            lines.append("")
            lines.append("Similar Historical Cases:")
            for case in similar_cases:
                lines.append(f"  [{int(case['similarity'] * 100)}%] {case['failure_type']}")
                if case.get("root_cause"):
                    lines.append(f"     Cause: {case['root_cause']}")
                if case.get("fix"):
                    lines.append(f"     Fix: {case['fix']}")

        return "\n".join(lines)

    def format_json(
        self,
        diagnoses: list[DiagnosisDict],
        metadata: FeatureMetadata,
        features: FeatureDict,
        decision: Optional[DecisionDict] = None,
        similar_cases: Optional[list] = None,
        runtime_info: Optional[dict] = None,
        parameter_warnings: Optional[list[dict]] = None,
        explain_data: Optional[dict] = None,
    ) -> str:
        return json.dumps(
            {
                "metadata": metadata,
                "runtime": runtime_info or {},
                "diagnoses": diagnoses,
                "decision": decision or {},
                "similar_cases": similar_cases or [],
                "parameter_warnings": parameter_warnings or [],
                "explain_data": explain_data or {},
                "features_summary": {
                    k: v for k, v in features.items() if not k.startswith("_")
                },
            },
            indent=2,
        )

    def format_html(
        self,
        diagnoses: list[DiagnosisDict],
        metadata: FeatureMetadata,
        features: FeatureDict,
        decision: Optional[DecisionDict] = None,
        similar_cases: Optional[list] = None,
        runtime_info: Optional[dict] = None,
        parameter_warnings: Optional[list[dict]] = None,
        explain_data: Optional[dict] = None,
    ) -> str:
        filename = metadata.get("log_file", "unknown").split("/")[-1]
        duration = metadata.get("duration_sec", 0.0)
        mins = int(duration // 60)
        secs = int(duration % 60)
        vehicle = f"{metadata.get('vehicle_type', 'Unknown')} {metadata.get('firmware', '')}".strip()

        sections = []
        quality_report = metadata.get("quality_report", {})
        if quality_report and isinstance(quality_report, dict) and quality_report.get("overall_status") != "UNKNOWN":
            overall_status = quality_report.get("overall_status", "RELIABLE")
            q_class = "healthy" if overall_status == "RELIABLE" else ("warning" if overall_status == "DEGRADED" else "critical")
            q_html = f'<h2><span class="badge {q_class}">{overall_status}</span> Log Quality & Capability Check</h2>'
            for cap_name, cap_info in quality_report.get("capabilities", {}).items():
                if isinstance(cap_info, dict) and cap_info.get("status") in ("DEGRADED", "UNSUPPORTED"):
                    c_status = cap_info.get("status", "")
                    c_class = "warning" if c_status == "DEGRADED" else "critical"
                    q_html += f'<div class="similar-case"><span class="badge {c_class}">{c_status}</span> <strong>{cap_name}:</strong> {cap_info.get("reason")}'
                    if cap_info.get("recommendation"):
                        q_html += f'<div style="margin-top:.3rem;color:#2471a3">-> Recommendation: {cap_info["recommendation"]}</div>'
                    q_html += '</div>'
            sections.append(f'<div class="card">{q_html}</div>')

        if runtime_info:
            sections.append(
                f'<div class="card"><strong>Runtime:</strong> {runtime_info.get("engine", "unknown")}</div>'
            )
            if (
                runtime_info.get("ml_available") is True
                and runtime_info.get("ml_confirmation_allowed") is False
            ):
                sections.append(
                    '<div class="card warning-box"><strong>ML status:</strong> '
                    "advisory only; calibration risk gates have not passed.</div>"
                )

        if parameter_warnings:
            warning_html = "".join(
                f'<div class="warning-box">{item["message"]}</div>' for item in parameter_warnings
            )
            sections.append(f'<div class="card"><h2>Pre-Flight & Parameter Validation</h2>{warning_html}</div>')

        if not diagnoses:
            decision_status = (decision or {}).get(
                "status",
                "no_fault_detected",
            )
            if decision_status == "insufficient_data":
                empty_class = "critical"
                empty_label = "INSUFFICIENT DATA"
                empty_text = (
                    "The available telemetry cannot support a reliable diagnosis."
                )
            elif decision_status == "uncertain":
                empty_class = "warning"
                empty_label = "UNCERTAIN"
                empty_text = (
                    "No fault crossed the threshold, but diagnostic capabilities "
                    "are degraded."
                )
            else:
                empty_class = "healthy"
                empty_label = "NO FAULT DETECTED"
                empty_text = (
                    "Supported checks found no reportable fault. This is not a "
                    "safe-to-fly certification."
                )
            sections.append(
                f'<div class="card"><span class="badge {empty_class}">'
                f"{empty_label}</span> {empty_text}</div>"
            )
        else:
            for diag in diagnoses:
                severity = diag["severity"].lower()
                badge = f'<span class="badge {severity}">{severity.upper()} {int(diag["confidence"] * 100)}%</span>'
                evidence = "".join(
                    f'<div class="evidence">{ev.get("feature")} = {ev.get("value")} (limit: {ev.get("threshold")})</div>'
                    for ev in diag.get("evidence", [])
                )
                sections.append(
                    f'<div class="card"><h2>{badge} {diag["failure_type"]}</h2>'
                    f'{evidence}<div class="fix">Fix: {diag["recommendation"]}</div>'
                    f'<div style="margin-top:.4rem;font-size:.8rem;color:#888">Method: {diag["detection_method"]}</div></div>'
                )

        hypotheses = (explain_data or {}).get("hypotheses", [])
        arbiter = (explain_data or {}).get("causal_arbiter", {})
        temporal_evidence = [
            item
            for item in (explain_data or {}).get("temporal_evidence", [])
            if item.get("status") == "satisfied"
        ]
        if temporal_evidence:
            items = "".join(
                f'<div class="hypothesis"><strong>{item["rule_id"]}:</strong> '
                f'{item["explanation"]}</div>'
                for item in temporal_evidence
            )
            sections.append(
                f'<div class="card"><h2>Temporal Logic Evidence</h2>{items}</div>'
            )
        matrix_profile = (explain_data or {}).get("matrix_profile", {})
        if matrix_profile.get("status") == "candidate":
            channels = ", ".join(
                str(item["channel"])
                for item in matrix_profile.get("contributing_channels", [])[:3]
            )
            sections.append(
                '<div class="card"><h2>Label-Free Temporal Discord</h2>'
                f'<div class="hypothesis">Candidate at '
                f'T+{float(matrix_profile.get("onset_sec", 0.0)):.1f}s '
                f'(score={float(matrix_profile.get("score", 0.0)):.3f}). '
                f'Leading channels: {channels or "not available"}. '
                "This is an anomaly candidate, not a failure label.</div></div>"
            )
        if hypotheses:
            items = []
            for idx, item in enumerate(hypotheses[:3], start=1):
                tanomaly = item.get("tanomaly", -1.0)
                time_text = _format_onset_time(tanomaly, metadata)
                items.append(
                    f'<div class="hypothesis"><strong>Hypothesis {idx}:</strong> '
                    f'{item["failure_type"]} via {item["source"]} '
                    f'({int(item["merged_confidence"] * 100)}%) from '
                    f'{item.get("lead_feature") or "telemetry correlation"} at {time_text}.</div>'
                )
            if arbiter:
                items.append(f'<div class="hypothesis"><strong>Causal Arbiter:</strong> {arbiter.get("reason", "no arbiter summary")}</div>')
            sections.append(f'<div class="card"><h2>Hypothesis Scaffolding</h2>{"".join(items)}</div>')

        if decision:
            subsystem_rows = ""
            for sub in (decision.get("ranked_subsystems") or [])[:5]:
                pct = int(sub["likelihood"] * 100)
                subsystem_rows += (
                    f"<tr><td>{sub['subsystem']}</td><td><span class=\"bar\" style=\"width:{pct * 2}px\"></span> {pct}%</td></tr>"
                )
            if subsystem_rows:
                sections.append(
                    '<div class="card"><h2>Subsystem Blame Ranking</h2>'
                    '<table class="subsystem-table"><tr><th>Subsystem</th><th>Likelihood</th></tr>'
                    f"{subsystem_rows}</table></div>"
                )

        if similar_cases:
            items = "".join(
                f'<div class="similar-case"><strong>[{int(case["similarity"] * 100)}%]</strong> {case["failure_type"]}</div>'
                for case in similar_cases
            )
            sections.append(f'<div class="card"><h2>Similar Historical Cases</h2>{items}</div>')

        return _HTML_TEMPLATE.format(
            filename=filename,
            duration=f"{mins}m {secs}s",
            vehicle=vehicle,
            body="".join(sections),
        )
