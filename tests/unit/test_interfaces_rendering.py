import builtins

import pytest

from src.interfaces.cli.rich_ui import render_dashboard
from src.interfaces.web.trajectory import render_trajectory_html


def test_dashboard_falls_back_without_rich(monkeypatch):
    real_import = builtins.__import__

    def import_without_rich(name, *args, **kwargs):
        if name.startswith("rich"):
            raise ImportError("Rich is optional")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_rich)
    rendered = render_dashboard(
        {"title": "Flight", "status": "FAIL", "failures": ["battery"]},
        [{"x": 0, "y": 0}, {"x": 1, "y": 1}],
    )

    assert "Flight" in rendered
    assert "Status: FAIL" in rendered
    assert "Failures: 1" in rendered
    assert "S" in rendered and "E" in rendered


def test_dashboard_uses_rich_when_available():
    pytest.importorskip("rich")
    rendered = render_dashboard({"title": "Flight", "status": "OK", "failures": []})

    assert "Flight" in rendered
    assert "OK" in rendered


def test_trajectory_html_escapes_title_and_maps_residuals():
    rendered = render_trajectory_html(
        [{"x": 1, "y": 2, "z": 3, "residual": 4}],
        title='<script>alert("x")</script>',
    )

    assert "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;" in rendered
    assert "<script>alert(\"x\")</script>" not in rendered
    assert "data.residual" in rendered
    assert "colorscale:'Turbo'" in rendered


@pytest.mark.parametrize(
    "points",
    [
        [{"x": 1, "y": 2, "z": 3, "residual": float("nan")}],
        [{"x": 1, "y": 2, "z": 3, "residual": float("inf")}],
        [None],
    ],
)
def test_trajectory_html_rejects_invalid_points(points):
    with pytest.raises((TypeError, ValueError)):
        render_trajectory_html(points)
