from __future__ import annotations

import json
from argparse import _SubParsersAction
from pathlib import Path

from src.analysis.weather_video import export_video_overlay, synchronize_video
from src.parser.bin_parser import LogParser


def register(subparsers: _SubParsersAction) -> None:
    parser = subparsers.add_parser("video-overlay", help="Export offline video timing as JSON, WebVTT, or SRT")
    parser.add_argument("logfile", help="Path to a supported flight log")
    parser.add_argument("--sync-points", required=True, help="JSON file containing [{log_time_us, video_sec}, ...]")
    parser.add_argument("--format", choices=["json", "vtt", "srt"], default="json")
    parser.add_argument("-o", "--output", required=True, help="Output sidecar path")
    parser.set_defaults(func=run)


def run(args) -> None:
    sync_path = Path(args.sync_points)
    with sync_path.open(encoding="utf-8") as handle:
        sync_points = json.load(handle)
    parsed = LogParser(args.logfile).parse()
    timestamps = [
        item["TimeUS"]
        for rows in (parsed.get("messages", {}) or {}).values()
        if isinstance(rows, list)
        for item in rows
        if isinstance(item, dict) and isinstance(item.get("TimeUS"), (int, float))
    ]
    sync = synchronize_video(timestamps, sync_points)
    destination = export_video_overlay(parsed, sync, args.output, format_name=args.format)
    print(f"Video timing sidecar saved to {destination}")

