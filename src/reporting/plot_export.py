"""Headless PNG chart generation for reports and agent integrations."""

from __future__ import annotations

import base64
from io import BytesIO
from typing import Any


def generate_plot(report: dict[str, Any], *, kind: str = "summary") -> dict[str, Any]:
    """Return a base64 PNG without writing files or requiring a display server."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:  # pragma: no cover - project dependency
        return {"schema_version": "plot-export.v1", "status": "dependency_unavailable", "reason": str(exc)}

    figure, axis = plt.subplots(figsize=(8, 4.5), dpi=120)
    if kind == "health":
        score = (report.get("health_score", {}) or {}).get("score", 0)
        modules = (report.get("health_score", {}) or {}).get("module_scores", {}) or {}
        labels = list(modules) or ["overall"]
        values = [float(modules[key]) for key in labels] if modules else [float(score)]
        axis.bar(labels, values, color="#2f80ed")
        axis.set_ylim(0, 100)
        axis.set_ylabel("Score / 100")
        axis.set_title(f"Flight health score: {score}/100")
        axis.tick_params(axis="x", rotation=25)
    elif kind == "diagnoses":
        diagnoses = report.get("diagnoses", []) or []
        labels = [str(item.get("failure_type", "unknown")) for item in diagnoses]
        values = [float(item.get("confidence", 0.0)) * 100.0 for item in diagnoses]
        if labels:
            axis.barh(labels[::-1], values[::-1], color="#d9534f")
        axis.set_xlim(0, 100)
        axis.set_xlabel("Confidence (%)")
        axis.set_title("Deterministic diagnosis confidence")
    else:
        features = report.get("features_summary", report.get("features", {})) or {}
        numeric = [(str(key), float(value)) for key, value in features.items() if isinstance(value, (int, float))][:12]
        labels = [item[0] for item in numeric]
        values = [item[1] for item in numeric]
        if labels:
            axis.bar(labels, values, color="#27ae60")
        axis.set_title("Numeric telemetry feature summary")
        axis.tick_params(axis="x", rotation=45, labelsize=8)
    axis.grid(axis="y", alpha=0.2)
    figure.tight_layout()
    buffer = BytesIO()
    figure.savefig(buffer, format="png", bbox_inches="tight")
    plt.close(figure)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return {"schema_version": "plot-export.v1", "status": "reliable", "kind": kind, "mime_type": "image/png", "encoding": "base64", "data": encoded, "byte_count": len(buffer.getvalue())}
