"""Colored terminal dashboard with an ASCII trajectory fallback."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any


def _trajectory(points: Sequence[Mapping[str, Any]], width: int = 48, height: int = 12) -> str:
    if not points:
        return "(trajectory unavailable)"
    coordinates = [(float(point.get("x", 0.0)), float(point.get("y", 0.0))) for point in points]
    xs, ys = zip(*coordinates)
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    canvas = [[" " for _ in range(width)] for _ in range(height)]
    for index, (x, y) in enumerate(coordinates):
        column = 0 if max_x == min_x else round((x - min_x) / (max_x - min_x) * (width - 1))
        row = height - 1 if max_y == min_y else height - 1 - round((y - min_y) / (max_y - min_y) * (height - 1))
        canvas[row][column] = "S" if index == 0 else "E" if index == len(coordinates) - 1 else "."
    return "\n".join("".join(row) for row in canvas)


def render_dashboard(summary: Mapping[str, Any], trajectory: Sequence[Mapping[str, Any]] = ()) -> str:
    """Render a compact dashboard, using Rich when present and ANSI otherwise."""

    title = str(summary.get("title", "ArduPilot Flight Diagnosis"))
    failures = summary.get("failures", [])
    status = str(summary.get("status", "UNKNOWN"))
    try:
        from rich.console import Console
        from rich.table import Table

        console = Console(record=True, width=100, color_system="standard")
        table = Table(title=title)
        table.add_column("Status")
        table.add_column("Failures")
        table.add_row(status, str(len(failures)))
        console.print(table)
        for failure in failures:
            console.print(f"[red]• {failure}[/red]")
        console.print(_trajectory(trajectory))
        return console.export_text(styles=True)
    except ImportError:
        lines = [f"\x1b[1m{title}\x1b[0m", f"Status: {status}", f"Failures: {len(failures)}"]
        lines.extend(f"\x1b[31m- {failure}\x1b[0m" for failure in failures)
        lines.append(_trajectory(trajectory))
        return "\n".join(lines)


def render_failure_score(value: float, width: int = 20) -> str:
    """Render a bounded text score without trusting arbitrary terminal escapes."""

    if not math.isfinite(value):
        raise ValueError("score must be finite")
    filled = round(max(0.0, min(1.0, value)) * width)
    return "[" + "#" * filled + "." * (width - filled) + "]"
