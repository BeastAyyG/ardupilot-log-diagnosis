from __future__ import annotations

import json
from argparse import _SubParsersAction
from pathlib import Path

from src.cli.commands.common import write_or_print_output
from src.fleet.store import FleetStore


def register(subparsers: _SubParsersAction) -> None:
    parser = subparsers.add_parser("fleet", help="Store and compare canonical reports in an operator-owned local SQLite database")
    sub = parser.add_subparsers(dest="fleet_command", required=True)

    add = sub.add_parser("add", help="Store one canonical JSON report")
    add.add_argument("report")
    add.add_argument("--aircraft-id", default="default")
    add.add_argument("--db", default="fleet_reports.sqlite3")
    add.set_defaults(func=run_add)

    trend = sub.add_parser("trend", help="Compare stored reports for one aircraft")
    trend.add_argument("--aircraft-id", default="default")
    trend.add_argument("--db", default="fleet_reports.sqlite3")
    trend.add_argument("--limit", type=int, default=100)
    trend.add_argument("-o", "--output")
    trend.set_defaults(func=run_trend)

    location = sub.add_parser("location", help="Find repeated coarse location/finding patterns without exposing exact coordinates")
    location.add_argument("--aircraft-id", default="default")
    location.add_argument("--db", default="fleet_reports.sqlite3")
    location.add_argument("--limit", type=int, default=100)
    location.add_argument("-o", "--output")
    location.set_defaults(func=run_location)

    search = sub.add_parser("search", help="Search local reports by aircraft, vehicle, firmware, filename, or health score")
    search.add_argument("--aircraft-id")
    search.add_argument("--vehicle")
    search.add_argument("--firmware")
    search.add_argument("--filename")
    search.add_argument("--min-health", type=float)
    search.add_argument("--max-health", type=float)
    search.add_argument("--limit", type=int, default=100)
    search.add_argument("--db", default="fleet_reports.sqlite3")
    search.add_argument("-o", "--output")
    search.set_defaults(func=run_search)

    event = sub.add_parser("maintenance", help="Record a local maintenance event")
    event.add_argument("--aircraft-id", default="default")
    event.add_argument("--event-type", required=True)
    event.add_argument("--note", required=True)
    event.add_argument("--db", default="fleet_reports.sqlite3")
    event.set_defaults(func=run_maintenance)


def run_add(args) -> None:
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    report_id = FleetStore(args.db).add_report(report, aircraft_id=args.aircraft_id, filename=Path(args.report).name)
    print(f"Stored local report {report_id} for aircraft {args.aircraft_id}")


def run_trend(args) -> None:
    result = FleetStore(args.db).trend(args.aircraft_id, limit=args.limit)
    write_or_print_output(json.dumps(result, indent=2, default=str), args.output, "Fleet trend")


def run_location(args) -> None:
    from src.analysis.operations_metrics import location_recurrence

    rows = FleetStore(args.db).list_reports(aircraft_id=args.aircraft_id, limit=args.limit)
    result = location_recurrence([row["report"] for row in rows])
    write_or_print_output(json.dumps(result, indent=2, default=str), args.output, "Location recurrence")


def run_search(args) -> None:
    result = FleetStore(args.db).search_reports(aircraft_id=args.aircraft_id, vehicle=args.vehicle, firmware=args.firmware, filename=args.filename, min_health=args.min_health, max_health=args.max_health, limit=args.limit)
    write_or_print_output(json.dumps({"schema_version": "fleet-search.v1", "status": "reliable" if result else "insufficient_data", "count": len(result), "reports": result}, indent=2, default=str), args.output, "Fleet search")


def run_maintenance(args) -> None:
    event_id = FleetStore(args.db).add_maintenance(args.aircraft_id, args.event_type, args.note)
    print(f"Stored local maintenance event {event_id} for aircraft {args.aircraft_id}")
