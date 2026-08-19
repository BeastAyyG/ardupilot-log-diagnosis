from __future__ import annotations

import asyncio
import math

from fastapi.testclient import TestClient

from src.integrations.read_only_tools import TOOL_DEFINITIONS, dispatch_tool
from src.web.app import app, mcp_read_only_rpc, tools_call, tools_manifest


def _events() -> dict[str, dict[str, float]]:
    return {
        "power": {"onset_us": 1_000.0, "score": 0.8},
        "propulsion": {"onset_us": 2_000.0, "score": 0.9},
        "impact": {"onset_us": 3_000.0, "score": 1.0},
    }


def test_new_tools_are_manifested_by_api_and_mcp():
    names = {item["name"] for item in TOOL_DEFINITIONS}
    assert {"diagnose_flight_log", "get_causal_dag", "get_param_diffs"} <= names
    assert {item["name"] for item in asyncio.run(tools_manifest())["tools"]} >= names
    mcp_tools = asyncio.run(mcp_read_only_rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}))
    assert {item["name"] for item in mcp_tools["result"]["tools"]} >= names


def test_http_tool_manifests_use_the_shared_read_only_definitions():
    client = TestClient(app)
    api_tools = client.get("/api/tools")
    assert api_tools.status_code == 200
    assert {item["name"] for item in api_tools.json()["tools"]} >= {
        "diagnose_flight_log",
        "get_causal_dag",
        "get_param_diffs",
    }

    mcp_tools = client.post("/mcp", json={"jsonrpc": "2.0", "id": 7, "method": "tools/list"})
    assert mcp_tools.status_code == 200
    assert {item["name"] for item in mcp_tools.json()["result"]["tools"]} >= {
        "diagnose_flight_log",
        "get_causal_dag",
        "get_param_diffs",
    }


def test_causal_dag_and_parameter_diff_are_inline_and_read_only():
    causal = dispatch_tool("get_causal_dag", {"events": _events(), "dependencies": [["power", "propulsion"], ["propulsion", "impact"]]})
    assert causal["schema_version"] == "get-causal-dag.v1"
    assert causal["status"] == "reliable"
    assert causal["causal_dag"]["root_cause"] == "power"
    assert causal["read_only"] is True

    diff = dispatch_tool(
        "get_param_diffs",
        {"before": {"ATC_RAT_RLL_P": 0.1}, "after": {"ATC_RAT_RLL_P": 0.2}},
    )
    assert diff["schema_version"] == "get-param-diffs.v1"
    assert diff["diff"]["changed_count"] == 1
    assert diff["read_only"] is True


def test_new_tools_reject_paths_and_malformed_boundaries():
    path_result = dispatch_tool("get_causal_dag", {"path": "flight.BIN", "events": _events()})
    assert path_result == {
        "schema_version": "read-only-tool-error.v1",
        "status": "invalid_argument",
        "error": "Filesystem path arguments are not accepted: path",
        "code": "PATH_ARGUMENT_REJECTED",
        "read_only": True,
    }

    missing = dispatch_tool("get_param_diffs", {"before": {}})
    assert missing["code"] == "MISSING_ARGUMENT"
    assert missing["read_only"] is True

    malformed = dispatch_tool("get_causal_dag", {"events": []})
    assert malformed["code"] == "INVALID_ARGUMENT"
    assert malformed["read_only"] is True


def test_diagnose_flight_log_returns_evidence_and_json_safe_values():
    samples = [math.sin(2 * math.pi * 10 * index / 100) for index in range(64)]
    acceleration = [[0.0, 0.0, 9.80665] for _ in range(7)]
    acceleration.append([0.0, 0.0, 40.0 * 9.80665])
    result = dispatch_tool(
        "diagnose_flight_log",
        {
            "parsed": {"messages": {"ATT": []}, "features": {"impact_accel_g": 40.0}},
            "times_us": [index * 1_000 for index in range(8)],
            "acceleration": acceleration,
            "velocity": [[20.0, 0.0, 0.0] for _ in range(7)] + [[0.0, 0.0, 0.0]],
            "events": _events(),
            "vibration": samples,
            "sample_rate_hz": 100.0,
            "nperseg": 32,
        },
    )
    assert result["schema_version"] == "diagnose-flight-log.v1"
    assert result["status"] in {"reliable", "degraded"}
    assert result["components"]["impact_boundary"]["result"]["detected"] is True
    assert result["components"]["causal_dag"]["result"]["root_cause"] == "power"
    assert result["read_only"] is True

    api_result = asyncio.run(tools_call({"name": "get_param_diffs", "arguments": {"before": {"A": 1}, "after": {"A": 2}}}))
    assert api_result["result"]["schema_version"] == "get-param-diffs.v1"
    assert api_result["read_only"] is True
