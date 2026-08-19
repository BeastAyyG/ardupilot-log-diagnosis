from __future__ import annotations

import json
from argparse import _SubParsersAction

from src.cli.commands.common import write_or_print_output, load_parsed_and_features
from src.reporting.hardware import HardwareReportBuilder


def register(subparsers: _SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "hardware",
        help="Report detected hardware, system health, log stats, and safe parameters",
    )
    parser.add_argument("logfile", help="Path to a supported .BIN/.LOG, .ULG/.ULOG, .TLOG, or optional .BBL/.BFL file")
    parser.add_argument(
        "--parameters",
        choices=["minimal", "changed", "all"],
        default="minimal",
        help="Parameter export mode (changed uses in-log PARM changes; minimal excludes calibration/RC values)",
    )
    parser.add_argument("--format", choices=["terminal", "json"], default="terminal")
    parser.add_argument("-o", "--output", help="Save report to file")
    parser.set_defaults(func=run)


def _terminal(report: dict) -> str:
    metadata = report["metadata"]
    health = report["system_health"]
    lines = [
        "=== Hardware and Configuration Report ===",
        f"Vehicle: {metadata['vehicle_type']}",
        f"Firmware: {metadata['firmware_version']}",
        f"Duration: {metadata['duration_sec']:.1f}s | Messages: {metadata['total_messages']}",
        f"File SHA256: {report['file'].get('sha256', 'unavailable')}",
        "",
        "Sensors:",
    ]
    for name, sensor in report["sensors"].items():
        state = "present" if sensor["present"] else "missing"
        types = ", ".join(sensor["message_types"]) or "-"
        lines.append(f"  {name}: {state} ({types}; {sensor['sample_count']} samples)")
    lines.extend([
        "",
        f"Errors: {health['error_count']}",
        f"Watchdog/internal error: {'yes' if health['watchdog_or_internal_error'] else 'no'}",
        f"Parameters exported: {report['parameters']['count']} ({report['parameters']['mode']})",
    ])
    quality = report.get("log_quality", {})
    if quality:
        lines.extend(["", f"Log quality: {quality.get('overall_status', 'UNKNOWN')}"])
        for item in quality.get("actionable_recommendations", [])[:5]:
            lines.append(f"  - {item}")
    return "\n".join(lines)


def run(args) -> None:
    parsed, _ = load_parsed_and_features(args.logfile)
    report = HardwareReportBuilder().build(parsed, parameter_mode=args.parameters)
    output = json.dumps(report, indent=2) if args.format == "json" else _terminal(report)
    write_or_print_output(output, args.output, "Hardware report")
