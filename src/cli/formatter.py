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

        if parameter_warnings:
            lines.append(_c("Pre-Flight & Parameter Validation", _YELLOW, _BOLD))
            for item in parameter_warnings:
                lines.append(f"  - {item['message']}")
            lines.append("")

        if not diagnoses:
            lines.append(_c("HEALTHY - No critical failures detected.", _GREEN, _BOLD))
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
        if hypotheses:
            lines.append(_c("Hypothesis Scaffolding", _BOLD))
            for idx, item in enumerate(hypotheses[:3], start=1):
                tanomaly = item.get("tanomaly", -1.0)
                time_text = (
                    f"T+{tanomaly / 1e6:.1f}s"
                    if isinstance(tanomaly, (int, float)) and tanomaly > 0
                    else "no onset timestamp"
                )
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
                lines.append(
                    f"Top Guess: {top_guess.upper()} ({int(float(decision.get('top_confidence', 0.0)) * 100)}%)"
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

        if runtime_info:
            lines.append("")
            lines.append(f"Runtime: {runtime_info.get('engine', 'unknown')}")
            if runtime_info.get("ml_available") is False:
                lines.append(f"ML Status: fallback ({runtime_info.get('ml_reason', 'ml unavailable')})")

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
        if runtime_info:
            sections.append(
                f'<div class="card"><strong>Runtime:</strong> {runtime_info.get("engine", "unknown")}</div>'
            )

        if parameter_warnings:
            warning_html = "".join(
                f'<div class="warning-box">{item["message"]}</div>' for item in parameter_warnings
            )
            sections.append(f'<div class="card"><h2>Pre-Flight & Parameter Validation</h2>{warning_html}</div>')

        if not diagnoses:
            sections.append('<div class="card"><span class="badge healthy">HEALTHY</span> No critical failures detected.</div>')
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
        if hypotheses:
            items = []
            for idx, item in enumerate(hypotheses[:3], start=1):
                tanomaly = item.get("tanomaly", -1.0)
                time_text = (
                    f"T+{tanomaly / 1e6:.1f}s"
                    if isinstance(tanomaly, (int, float)) and tanomaly > 0
                    else "no onset timestamp"
                )
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
