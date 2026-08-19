"""Compare command for multi-flight trend analysis."""

from __future__ import annotations

import json
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path
from argparse import _SubParsersAction
from typing import Any, List, Dict

from src.comparison.trend_analyzer import TrendAnalyzer
from src.diagnosis.hybrid_engine import HybridEngine
from src.cli.commands.common import diagnose_with_windowed_ml
from src.parser.bin_parser import LogParser
from src.features.pipeline import FeaturePipeline
from src.reporting.hardware import HardwareReportBuilder

from .common import write_or_print_output


def register(subparsers: _SubParsersAction) -> None:
    """Register the compare command."""
    parser = subparsers.add_parser(
        "compare",
        help="Compare multiple flight logs for trend analysis and degradation detection"
    )
    parser.add_argument(
        "logfiles",
        nargs="+",
        help="Paths to .BIN files to compare (minimum 2)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON format"
    )
    parser.add_argument(
        "--format",
        choices=["terminal", "json", "html"],
        default="terminal",
        help="Output format: terminal (default), json, or html"
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Save report to file"
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable caching of analysis results"
    )
    parser.set_defaults(func=run)


def run(args) -> None:
    """Execute the compare command."""
    json_mode = args.json or getattr(args, "format", "terminal") == "json"

    def progress(message: str) -> None:
        print(message, file=sys.stderr if json_mode else sys.stdout)

    if len(args.logfiles) < 2:
        progress("Error: At least 2 log files required for comparison")
        return
    
    # Analyze each flight
    analysis_results: List[Dict[str, Any]] = []
    
    progress(f"Analyzing {len(args.logfiles)} flights...")
    
    engine = HybridEngine()
    parser_obj = LogParser("")
    pipeline = FeaturePipeline()
    seen_source_hashes: set[str] = set()
    
    for i, logfile in enumerate(args.logfiles, 1):
        logpath = Path(logfile)
        if not logpath.exists():
            progress(f"Warning: File not found: {logfile}, skipping...")
            continue
        
        progress(f"  [{i}/{len(args.logfiles)}] Analyzing {logpath.name}...")
        
        # Pymavlink can print malformed-header diagnostics directly to stdout.
        # Capture it so `--json` stays valid JSON and reject the malformed log
        # cleanly instead of allowing downstream feature extraction to fail.
        try:
            parser_obj.filepath = str(logpath)
            with redirect_stdout(io.StringIO()):
                parsed = parser_obj.parse()
        except Exception as exc:
            progress(f"Warning: Could not parse {logpath.name}; skipping ({exc}).")
            continue
        parse_metadata = parsed.get("metadata", {}) or {}
        if not parse_metadata.get("parse_complete", False):
            detail = parse_metadata.get("parse_error") or "parser did not complete"
            progress(f"Warning: Invalid log {logpath.name}; skipping ({detail}).")
            continue
        source_hash = str((parse_metadata.get("file_format", {}) or {}).get("sha256") or "")
        if source_hash and source_hash in seen_source_hashes:
            progress(f"Warning: Duplicate flight {logpath.name}; skipping.")
            continue
        if source_hash:
            seen_source_hashes.add(source_hash)
        
        # Extract features
        features = pipeline.extract(parsed)
        if not (features.get("_metadata", {}) or {}).get("extraction_success", True):
            progress(f"Warning: Feature extraction failed for {logpath.name}; skipping.")
            continue
        
        # Run diagnosis
        diagnoses, _ = diagnose_with_windowed_ml(engine, parsed, features)
        # Build analysis result
        metadata = dict(features.get("_metadata", {}) or {})
        metadata.setdefault("filename", logpath.name)
        metadata.setdefault("log_file", str(logpath))
        
        analysis_results.append({
            "metadata": metadata,
            "features": features,
            "diagnoses": diagnoses,
            "hardware_report": HardwareReportBuilder().build(parsed, parameter_mode="minimal", diagnoses=diagnoses),
        })
    
    if len(analysis_results) < 2:
        message = "Need at least 2 distinct valid log files for comparison"
        progress(f"Error: {message}")
        if json_mode:
            write_or_print_output(
                json.dumps(
                    {
                        "schema_version": "trend-report.v2",
                        "status": "insufficient_data",
                        "flights_analyzed": len(analysis_results),
                        "reason": message,
                    },
                    indent=2,
                ),
                args.output,
                "Comparison Report",
            )
        return
    
    # Run trend analysis
    progress("\nRunning trend analysis...")
    analyzer = TrendAnalyzer()
    trend_report = analyzer.compare_flights(analysis_results)
    
    # Format output
    if json_mode:
        output = json.dumps(trend_report, indent=2)
    elif getattr(args, "format", "terminal") == "html":
        output = _format_html_comparison(trend_report)
    else:
        output = _format_terminal_comparison(trend_report)
    
    write_or_print_output(output, args.output, "Comparison Report")


def _format_terminal_comparison(report: Dict[str, Any]) -> str:
    """Format comparison report for terminal output."""
    lines = []
    lines.append("=" * 60)
    lines.append("MULTI-FLIGHT TREND ANALYSIS")
    lines.append("=" * 60)
    lines.append("")
    
    # Summary
    summary = report.get("summary", "No summary available")
    lines.append(summary)
    lines.append("")
    
    # Flight order
    lines.append("Flights Analyzed:")
    for i, filename in enumerate(report.get("flight_order", []), 1):
        lines.append(f"  {i}. {filename}")
    lines.append("")
    
    # Key trends
    lines.append("-" * 60)
    lines.append("KEY TRENDS")
    lines.append("-" * 60)
    
    trends = report.get("trends", {})
    for metric, data in trends.items():
        if metric == "diagnosis" or not isinstance(data, dict):
            continue
        
        change_pct = data.get("change_percent", 0)
        arrow = "↑" if change_pct > 0 else ("↓" if change_pct < 0 else "→")
        
        lines.append(f"{metric.replace('_', ' ').title()}: {arrow} {abs(change_pct):.1f}%")
    
    lines.append("")
    
    # Insights
    insights = report.get("insights", [])
    if insights:
        lines.append("-" * 60)
        lines.append("ACTIONABLE INSIGHTS")
        lines.append("-" * 60)
        
        for insight in insights[:5]:  # Show top 5
            severity_icon = {"critical": "🔴", "warning": "🟡", "info": "ℹ️"}.get(
                insight.get("severity", "info"), "ℹ️"
            )
            lines.append(f"{severity_icon} {insight.get('message', '')}")
            lines.append(f"   → {insight.get('recommendation', '')}")
            lines.append("")
    
    return "\n".join(lines)


def _format_html_comparison(report: Dict[str, Any]) -> str:
    """Format comparison report as HTML."""
    html = [
        "<!DOCTYPE html>",
        "<html><head><title>Multi-Flight Trend Analysis</title>",
        "<style>",
        "body { font-family: Arial, sans-serif; margin: 40px; background: #1a1a2e; color: #eee; }",
        ".card { background: #16213e; padding: 20px; margin: 20px 0; border-radius: 8px; }",
        ".critical { border-left: 4px solid #ef4444; }",
        ".warning { border-left: 4px solid #f59e0b; }",
        ".info { border-left: 4px solid #3b82f6; }",
        "h1 { color: #00d9ff; }",
        "h2 { color: #00d9ff; margin-top: 30px; }",
        ".trend-up { color: #ef4444; }",
        ".trend-down { color: #10b981; }",
        "</style>",
        "</head><body>",
        "<h1>📊 Multi-Flight Trend Analysis</h1>",
    ]
    
    # Summary
    html.append(f"<div class='card'><pre>{report.get('summary', '')}</pre></div>")
    
    # Trends
    html.append("<h2>Key Trends</h2><div class='card'>")
    trends = report.get("trends", {})
    for metric, data in trends.items():
        if metric == "diagnosis" or not isinstance(data, dict):
            continue
        change_pct = data.get("change_percent", 0)
        direction_class = "trend-up" if change_pct > 0 else ("trend-down" if change_pct < 0 else "")
        html.append(f"<p>{metric.replace('_', ' ').title()}: <span class='{direction_class}'>{change_pct:+.1f}%</span></p>")
    html.append("</div>")
    
    # Insights
    html.append("<h2>Actionable Insights</h2>")
    for insight in report.get("insights", []):
        severity = insight.get("severity", "info")
        html.append(f"<div class='card {severity}'>")
        html.append(f"<strong>{insight.get('message', '')}</strong>")
        html.append(f"<p>{insight.get('recommendation', '')}</p>")
        html.append("</div>")
    
    html.append("</body></html>")
    return "\n".join(html)
