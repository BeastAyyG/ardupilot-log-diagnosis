"""Compare command for multi-flight trend analysis."""

from __future__ import annotations

import json
from pathlib import Path
from argparse import _SubParsersAction
from typing import Any, List, Dict

from src.comparison.trend_analyzer import TrendAnalyzer
from src.cli.formatter import DiagnosisFormatter
from src.diagnosis.hybrid_engine import HybridEngine
from src.diagnosis.decision_policy import evaluate_decision
from src.parser.bin_parser import LogParser
from src.features.pipeline import FeaturePipeline

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
    if len(args.logfiles) < 2:
        print("Error: At least 2 log files required for comparison")
        return
    
    # Analyze each flight
    analysis_results: List[Dict[str, Any]] = []
    
    print(f"Analyzing {len(args.logfiles)} flights...")
    
    engine = HybridEngine()
    parser_obj = LogParser("")
    pipeline = FeaturePipeline()
    
    for i, logfile in enumerate(args.logfiles, 1):
        logpath = Path(logfile)
        if not logpath.exists():
            print(f"Warning: File not found: {logfile}, skipping...")
            continue
        
        print(f"  [{i}/{len(args.logfiles)}] Analyzing {logpath.name}...")
        
        # Parse log
        parser_obj.filepath = str(logpath)
        parsed = parser_obj.parse()
        
        # Extract features
        features = pipeline.extract(parsed)
        
        # Run diagnosis
        diagnoses = engine.diagnose(features)
        decision = evaluate_decision(diagnoses)
        
        # Build analysis result
        formatter = DiagnosisFormatter()
        metadata = features.get("_metadata", {})
        
        result = formatter.format_json(
            diagnoses,
            metadata,
            features,
            decision=decision,
            similar_cases=[],
            runtime_info={"engine": "hybrid"},
            parameter_warnings=[],
            explain_data=None,
        )
        
        analysis_results.append(result)
    
    if len(analysis_results) < 2:
        print("Error: Need at least 2 valid log files for comparison")
        return
    
    # Run trend analysis
    print("\nRunning trend analysis...")
    analyzer = TrendAnalyzer()
    trend_report = analyzer.compare_flights(analysis_results)
    
    # Format output
    if args.json or getattr(args, "format", "terminal") == "json":
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
