from __future__ import annotations

import json
from argparse import _SubParsersAction

from src.analysis.mission_plan import mission_compliance_report, validate_mission
from src.cli.commands.common import load_parsed_and_features, write_or_print_output


def register(subparsers: _SubParsersAction) -> None:
    parser = subparsers.add_parser("mission", help="Validate a mission or compare it with a flight track")
    parser.add_argument("mission", help="Mission JSON file or QGC WPL text file")
    parser.add_argument("logfile", nargs="?", help="Optional supported flight log for compliance review")
    parser.add_argument("--geofence", help="Optional JSON file containing fence points")
    parser.add_argument("--rally-points", dest="rally_points", help="Optional JSON file containing rally points")
    parser.add_argument("--tolerance-m", type=float, default=30.0, help="Waypoint compliance tolerance in metres")
    parser.add_argument("-o", "--output", help="Save JSON output")
    parser.set_defaults(func=run)


def _load_json_or_text(path: str):
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def run(args) -> None:
    mission = _load_json_or_text(args.mission)
    geofence = _load_json_or_text(args.geofence) if args.geofence else None
    rally_points = _load_json_or_text(args.rally_points) if args.rally_points else None
    if args.logfile:
        parsed, _features = load_parsed_and_features(args.logfile)
        result = mission_compliance_report(parsed, mission, tolerance_m=args.tolerance_m, geofence=geofence)
    else:
        result = validate_mission(mission, geofence=geofence, rally_points=rally_points)
    write_or_print_output(json.dumps(result, indent=2, default=str), args.output, "Mission review")
