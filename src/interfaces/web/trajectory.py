"""Self-contained offline SVG trajectory viewer with residual color metadata."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from html import escape
from numbers import Real
from typing import Any


def _json(value: Any) -> str:
    """Serialize script data without allowing HTML or JavaScript termination."""

    serialized = json.dumps(value, separators=(",", ":"), allow_nan=False)
    return (
        serialized.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"point field {field!r} must be finite and numeric")
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"point field {field!r} must be finite and numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"point field {field!r} must be finite and numeric")
    return number


def render_trajectory_html(
    points: Sequence[Mapping[str, Any]], *, title: str = "Flight residual trajectory"
) -> str:
    """Return a valid offline HTML page with an inline SVG trajectory viewer."""

    if not points or len(points) > 100_000:
        raise ValueError("points must contain between one and 100000 samples")
    columns: dict[str, list[float]] = {
        key: [] for key in ("x", "y", "z", "residual")
    }
    for point in points:
        if not isinstance(point, Mapping):
            raise TypeError("points must contain mappings")
        for key, values in columns.items():
            if key not in point:
                raise ValueError(f"point field {key!r} must be finite and numeric")
            values.append(_finite_number(point[key], key))

    safe_title = escape(str(title), quote=True)
    payload = _json({"type": "scatter3d", "colorscale": "Turbo", **columns})
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{safe_title}</title>
<style>
:root {{ color-scheme: dark; font: 16px system-ui,sans-serif; }}
body {{ margin: 0; background: #111827; color: #e5e7eb; }}
main {{ max-width: 900px; margin: auto; padding: 1rem; }}
h1 {{ font-size: 1.25rem; margin: 0 0 .25rem; }}
.offline {{ color: #9ca3af; margin: 0 0 1rem; }}
svg {{ width: 100%; height: auto; background: #0b1220; border: 1px solid #374151; }}
.axis {{ stroke: #374151; stroke-width: 1; }}
.trajectory {{ fill: none; stroke: #2ccf8c; stroke-width: 3; stroke-linejoin: round; }}
.marker {{ stroke: #fff; stroke-width: 2; }}
.legend {{ fill: #9ca3af; font-size: 12px; }}
</style>
</head>
<body>
<main>
<h1>{safe_title}</h1>
<p class="offline">Offline viewer · residual magnitude uses the Turbo trace scale.</p>
<svg id="trajectory" viewBox="0 0 760 440" role="img" aria-label="{safe_title}">
<line class="axis" x1="24" y1="416" x2="736" y2="416"></line>
<line class="axis" x1="24" y1="24" x2="24" y2="416"></line>
<polyline id="trajectory-line" class="trajectory" points=""></polyline>
<circle id="start-marker" class="marker" r="5"></circle>
<circle id="end-marker" class="marker" r="5"></circle>
<text class="legend" x="32" y="40">North / East projection · z contributes depth</text>
</svg>
</main>
<script id="trajectory-data" type="application/json">{payload}</script>
<script>
(() => {{
  const trace = {{type:'scatter3d', colorscale:'Turbo', ...JSON.parse(
    document.getElementById('trajectory-data').textContent
  )}};
  const data = trace;
  document.getElementById('trajectory').setAttribute('data-residual-count', data.residual.length);
  const width = 760, height = 440, pad = 32;
  const projected = trace.x.map((x, i) => [x - trace.z[i] * 0.35, trace.y[i] - trace.z[i] * 0.2]);
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  let minResidual = Infinity, maxResidual = -Infinity;
  for (let i = 0; i < projected.length; i += 1) {{
    minX = Math.min(minX, projected[i][0]); maxX = Math.max(maxX, projected[i][0]);
    minY = Math.min(minY, projected[i][1]); maxY = Math.max(maxY, projected[i][1]);
    minResidual = Math.min(minResidual, trace.residual[i]);
    maxResidual = Math.max(maxResidual, trace.residual[i]);
  }}
  const sx = (width - 2 * pad) / (maxX - minX || 1);
  const sy = (height - 2 * pad) / (maxY - minY || 1);
  const scale = Math.min(sx, sy);
  const point = ([x, y]) => [pad + (x - minX) * scale, height - pad - (y - minY) * scale];
  const points = projected.map(point);
  document.getElementById('trajectory-line').setAttribute(
    'points', points.map(([x, y]) => `${{x.toFixed(2)}},${{y.toFixed(2)}}`).join(' ')
  );
  const palette = ['#30123b', '#4145ab', '#2a9fd6', '#2ccf8c', '#a3e635', '#f9e721'];
  const colorFor = value => {{
    const ratio = (value - minResidual) / (maxResidual - minResidual || 1);
    return palette[Math.min(palette.length - 1, Math.floor(Math.max(0, ratio) * palette.length))];
  }};
  [0, points.length - 1].filter((value, index, values) => values.indexOf(value) === index).forEach((i, markerIndex) => {{
    const marker = document.getElementById(markerIndex ? 'end-marker' : 'start-marker');
    marker.setAttribute('cx', points[i][0]); marker.setAttribute('cy', points[i][1]);
    marker.setAttribute('fill', colorFor(trace.residual[i]));
  }});
}})();
</script>
</body>
</html>"""
