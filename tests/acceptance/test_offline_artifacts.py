from __future__ import annotations

import json

import pytest

from src.core.causality.cita_dag import build_cita_dag
from src.core.remediation.safety_clamper import clamp_parameter_changes
from src.interfaces.mcp_server.server import MCPServer, ToolSpec
from src.interfaces.web.trajectory import render_trajectory_html


def _causal_fixture() -> dict[str, object]:
    return build_cita_dag(
        {
            "battery": {"onset_us": 1_000_000, "score": 0.95},
            "motor_4": {"onset_us": 2_000_000, "score": 0.90},
            "attitude": {"onset_us": 3_000_000, "score": 0.80},
            "impact": {"onset_us": 4_000_000, "score": 1.0},
        },
        dependencies=[
            ("battery", "motor_4"),
            ("motor_4", "attitude"),
            ("attitude", "impact"),
        ],
        impact_boundary_us=4_000_000,
    ).as_dict()


def test_offline_mcp_call_returns_causal_artifact_without_network():
    causal = _causal_fixture()
    server = MCPServer(
        [
            ToolSpec(
                "get_causal_dag",
                "Return the local deterministic causal DAG.",
                lambda _arguments: causal,
            )
        ]
    )

    initialize = server.handle_request(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize"}
    )
    called = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "get_causal_dag", "arguments": {}},
        }
    )

    assert initialize is not None
    assert initialize["result"]["serverInfo"]["name"] == "ardupilot-log-diagnosis"
    assert called is not None
    payload = json.loads(called["result"]["content"][0]["text"])
    assert payload["root_cause"] == "battery"
    assert {"from": "battery", "to": "motor_4"} in payload["edges"]
    assert payload["impact_boundary_us"] == 4_000_000


def test_visualization_contains_residual_artifact_and_rejects_external_runtime():
    html = render_trajectory_html(
        [
            {"x": 0, "y": 0, "z": 0, "residual": 0.1},
            {"x": 1, "y": 2, "z": -1, "residual": 2.5},
        ],
        title="<offline flight>",
    )

    assert "scatter3d" in html
    assert "Turbo" in html
    assert "&lt;offline flight&gt;" in html
    assert "https://cdn.plot.ly" not in html, (
        "offline visualization must not depend on a CDN"
    )


def test_causal_chain_excludes_terminal_impact_node():
    causal = _causal_fixture()

    assert causal["root_cause"] == "battery"
    assert causal["topological_order"] == ["battery", "motor_4", "attitude"]
    assert causal["edges"] == [
        {"from": "battery", "to": "motor_4"},
        {"from": "motor_4", "to": "attitude"},
    ]


def test_parameter_diff_is_bounded_and_serializable():
    result = clamp_parameter_changes(
        {"ATC_RAT_RLL_P": 100.0, "INS_HNTCH_FREQ": 180.0},
        {"ATC_RAT_RLL_P": 150.0, "INS_HNTCH_FREQ": 200.0},
    )

    assert result.param_lines == ("ATC_RAT_RLL_P,125", "INS_HNTCH_FREQ,200")
    assert result.mavlink_packets[0]["command"] == "PARAM_SET"
    assert result.changes[0].was_clamped is True
    assert result.changes[1].was_clamped is False


def test_invalid_visualization_values_fail_instead_of_being_fabricated():
    with pytest.raises(ValueError, match="finite"):
        render_trajectory_html([{"x": 0, "y": 0, "z": 0, "residual": float("nan")}])
