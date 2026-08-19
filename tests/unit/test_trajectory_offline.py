import json
import re

import pytest

from src.interfaces.web.trajectory import _json, render_trajectory_html


def _points():
    return [
        {"x": 0.0, "y": 0.0, "z": 1.0, "residual": 0.1},
        {"x": 2.0, "y": 1.0, "z": 3.0, "residual": 0.8},
        {"x": 4.0, "y": 2.0, "z": 2.0, "residual": 0.3},
    ]


def _metadata(html):
    match = re.search(
        r'<script id="trajectory-data" type="application/json">(.*?)</script>',
        html,
        re.DOTALL,
    )
    assert match is not None
    return json.loads(match.group(1))


def test_render_is_self_contained_and_preserves_trace_metadata():
    html = render_trajectory_html(_points())

    assert html.startswith("<!doctype html>")
    assert "<style>" in html and "<svg" in html and "<script>" in html
    assert "http://" not in html and "https://" not in html
    assert "<link" not in html and " src=" not in html
    assert "type:'scatter3d'" in html and "colorscale:'Turbo'" in html
    assert _metadata(html) == {
        "type": "scatter3d",
        "colorscale": "Turbo",
        "x": [0.0, 2.0, 4.0],
        "y": [0.0, 1.0, 2.0],
        "z": [1.0, 3.0, 2.0],
        "residual": [0.1, 0.8, 0.3],
    }


def test_representative_svg_rendering_contains_projection_and_markers():
    html = render_trajectory_html(_points(), title="Offline flight")

    assert '<title>Offline flight</title>' in html
    assert 'id="trajectory-line"' in html
    assert 'id="start-marker"' in html and 'id="end-marker"' in html
    assert "North / East projection" in html
    assert "colorFor" in html and "data.residual" in html


def test_title_and_script_payload_are_escaped():
    html = render_trajectory_html(
        _points(),
        title='</title><script>window.pwned=1</script><img src=x onerror=1>',
    )

    assert "<script>window.pwned" not in html
    assert "<img src=x" not in html
    assert "&lt;/title&gt;&lt;script&gt;window.pwned=1&lt;/script&gt;" in html
    payload = _json({"value": "</script><script>alert(1)</script>"})
    assert "</script>" not in payload
    assert r"\u003c" in payload and r"\u003e" in payload
    with pytest.raises(ValueError):
        _json({"value": float("nan")})


@pytest.mark.parametrize(
    "points",
    [
        [],
        [None],
        [{"x": 0, "y": 0, "z": 0}],
        [{"x": 0, "y": 0, "z": 0, "residual": "bad"}],
        [{"x": float("nan"), "y": 0, "z": 0, "residual": 0}],
        [{"x": 0, "y": 0, "z": float("inf"), "residual": 0}],
        [{"x": True, "y": 0, "z": 0, "residual": 0}],
    ],
)
def test_rejects_malformed_or_nonfinite_points(points):
    with pytest.raises((TypeError, ValueError)):
        render_trajectory_html(points)


def test_rejects_more_than_100000_points():
    point = {"x": 0.0, "y": 0.0, "z": 0.0, "residual": 0.0}

    with pytest.raises(ValueError, match="100000"):
        render_trajectory_html([point] * 100_001)
