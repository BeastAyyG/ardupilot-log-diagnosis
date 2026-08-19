"""Portable HTML/PDF report helpers from canonical structured results."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def _text(value: Any) -> str:
    return html.escape(str(value if value is not None else "-"))


def _flatten_findings(report: dict[str, Any]) -> list[dict[str, Any]]:
    hardware = report.get("hardware_report", report)
    values = hardware.get("safety_findings", []) if isinstance(hardware, dict) else []
    return [item for item in values if isinstance(item, dict)]


def export_pdf(report: dict[str, Any], output_path: str | Path) -> Path:
    """Write a reviewable PDF with evidence and a stable schema/hash footer."""

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="TitleCenter", parent=styles["Title"], alignment=TA_CENTER, textColor=colors.HexColor("#17324d")))
    styles.add(ParagraphStyle(name="Small", parent=styles["Normal"], fontSize=8, leading=10, textColor=colors.HexColor("#4a5568")))
    styles.add(ParagraphStyle(name="Section", parent=styles["Heading2"], textColor=colors.HexColor("#17324d"), spaceBefore=8, spaceAfter=5))
    styles.add(ParagraphStyle(name="Finding", parent=styles["Normal"], fontSize=8.5, leading=11))

    metadata = report.get("metadata", {})
    hardware = report.get("hardware_report", {})
    if not hardware:
        hardware = report
    diagnoses = report.get("diagnoses", [])
    decision = report.get("decision", report.get("explain_data", {}).get("decision", {}))
    health_score = report.get("health_score", {}) or {}
    file_info = hardware.get("file", {}) if isinstance(hardware, dict) else {}

    story = [
        Paragraph("ArduPilot Flight Analysis Report", styles["TitleCenter"]),
        Paragraph(
            f"Schema: {_text(report.get('schema_version', 'analysis.v1'))} | "
            f"Log: {_text(metadata.get('filename', file_info.get('path', 'unknown')))} | "
            f"Vehicle: {_text(metadata.get('vehicle', hardware.get('metadata', {}).get('vehicle_type', 'Unknown')))}",
            styles["Small"],
        ),
        Spacer(1, 5 * mm),
        Paragraph("Decision", styles["Section"]),
    ]
    decision_rows = [
        ["Status", decision.get("status", "unknown")],
        ["Top guess", decision.get("top_guess", "none")],
        ["Confidence", f"{float(decision.get('top_confidence', 0.0)):.1%}" if isinstance(decision.get("top_confidence", 0.0), (int, float)) else "-"],
        ["Requires human review", decision.get("requires_human_review", False)],
        ["Input SHA256", file_info.get("sha256", "unavailable")],
    ]
    decision_table = Table([[Paragraph(_text(k), styles["Small"]), Paragraph(_text(v), styles["Finding"])] for k, v in decision_rows], colWidths=[45 * mm, 125 * mm])
    decision_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#edf2f7")),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(decision_table)
    if health_score:
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(
            f"Health score: <b>{_text(health_score.get('score', '-'))}/100</b> "
            f"({_text(health_score.get('label', 'review'))}). Review-priority only; not a safe-to-fly certification.",
            styles["Finding"],
        ))
    story.append(Paragraph("Diagnoses", styles["Section"]))
    if diagnoses:
        for diagnosis in diagnoses:
            evidence = "; ".join(
                f"{item.get('feature')}: {item.get('value')} (limit {item.get('threshold')})"
                for item in diagnosis.get("evidence", [])
            )
            story.append(Paragraph(
                f"<b>{_text(diagnosis.get('failure_type'))}</b> - "
                f"{float(diagnosis.get('confidence', 0.0)):.1%} - "
                f"{_text(diagnosis.get('recommendation'))}<br/>"
                f"<font size='8'>{_text(evidence or 'No structured evidence')}</font>",
                styles["Finding"],
            ))
            story.append(Spacer(1, 2 * mm))
    else:
        story.append(Paragraph("No diagnosis was emitted.", styles["Finding"]))

    story.append(PageBreak())
    story.append(Paragraph("Hardware and Log Quality", styles["Section"]))
    hardware_meta = hardware.get("metadata", {})
    hardware_rows = [
        ["Firmware", hardware_meta.get("firmware_version", "Unknown")],
        ["Vehicle", hardware_meta.get("vehicle_type", "Unknown")],
        ["Duration (s)", hardware_meta.get("duration_sec", 0.0)],
        ["Messages", hardware_meta.get("total_messages", 0)],
        ["Errors", hardware.get("system_health", {}).get("error_count", 0)],
        ["Watchdog/internal error", hardware.get("system_health", {}).get("watchdog_or_internal_error", False)],
    ]
    table = Table([[Paragraph(_text(k), styles["Small"]), Paragraph(_text(v), styles["Finding"])] for k, v in hardware_rows], colWidths=[65 * mm, 105 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#edf2f7")),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e0")),
    ]))
    story.append(table)
    story.append(Paragraph("Safety findings", styles["Section"]))
    findings = _flatten_findings(report)
    for finding in findings:
        if finding.get("status") == "clear":
            continue
        evidence = json.dumps(finding.get("evidence", []), ensure_ascii=True)
        story.append(Paragraph(
            f"<b>{_text(finding.get('check_id'))}</b> [{_text(finding.get('severity'))}] "
            f"{_text(finding.get('recommendation'))}<br/>"
            f"<font size='7'>Evidence: {_text(evidence)}<br/>Source: {_text(finding.get('source_url'))}</font>",
            styles["Finding"],
        ))
        story.append(Spacer(1, 1.5 * mm))

    story.append(PageBreak())
    story.append(Paragraph("Sensor and Tuning Metrics", styles["Section"]))
    sensors = hardware.get("sensor_metrics", {})
    for name in ("battery", "compass", "gps", "imu", "esc"):
        value = sensors.get(name, {})
        story.append(Paragraph(f"<b>{_text(name.title())}</b>: {_text(json.dumps(value, ensure_ascii=True))}", styles["Finding"]))
        story.append(Spacer(1, 1.5 * mm))
    tuning = hardware.get("tuning_metrics", {})
    story.append(Paragraph("<b>Tuning analysis</b>: " + _text(json.dumps(tuning, ensure_ascii=True)), styles["Finding"]))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(
        "This report is read-only. Recommendations require human review and are not written to the flight controller.",
        styles["Small"],
    ))

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#718096"))
        canvas.drawString(18 * mm, 10 * mm, "ArduPilot Log Diagnosis")
        canvas.drawRightString(192 * mm, 10 * mm, f"Page {document.page}")
        canvas.restoreState()

    document = SimpleDocTemplate(
        str(destination),
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=15 * mm,
        bottomMargin=17 * mm,
        title="ArduPilot Flight Analysis Report",
        author="ArduPilot Log Diagnosis",
    )
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return destination
