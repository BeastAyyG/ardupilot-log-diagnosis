import io
import json

import pytest

from src.interfaces.mcp_server.server import MCPServer, ToolSpec


@pytest.fixture
def server():
    return MCPServer(
        [
            ToolSpec(
                name="echo",
                description="Return the supplied value.",
                handler=lambda arguments: {"value": arguments.get("value")},
            )
        ]
    )


def test_json_rpc_lifecycle_and_tool_call(server):
    initialized = server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert initialized["result"]["protocolVersion"] == "2024-11-05"

    ping = server.handle_request({"jsonrpc": "2.0", "id": 2, "method": "ping"})
    assert ping == {"jsonrpc": "2.0", "id": 2, "result": {}}

    listed = server.handle_request({"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
    assert listed["result"]["tools"][0]["name"] == "echo"
    assert listed["result"]["tools"][0]["inputSchema"] == {"type": "object"}

    called = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "echo", "arguments": {"value": "ok"}},
        }
    )
    assert called["result"]["structuredContent"] == {"value": "ok"}
    assert json.loads(called["result"]["content"][0]["text"]) == {"value": "ok"}


def test_notifications_emit_no_response_and_unknown_method_is_an_error(server):
    assert server.handle_request({"jsonrpc": "2.0", "method": "ping"}) is None
    assert server.handle_request({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    assert server.handle_request({"jsonrpc": "2.0", "method": "not-a-method"}) is None

    invalid = server.handle_request({"jsonrpc": "1.0", "id": 5, "method": "ping"})
    assert invalid["error"]["code"] == -32600


def test_stdio_round_trip_skips_notification_and_reports_bad_input(server):
    oversized = json.dumps({"jsonrpc": "2.0", "id": 9, "method": "ping", "padding": "x" * 2_000})
    source = io.StringIO(
        json.dumps({"jsonrpc": "2.0", "id": 6, "method": "ping"})
        + "\n"
        + json.dumps({"jsonrpc": "2.0", "method": "ping"})
        + "\n{not-json}\n"
        + oversized
        + "\n"
    )
    destination = io.StringIO()

    server.max_message_bytes = 1_024
    server.serve_stdio(source, destination)

    responses = [json.loads(line) for line in destination.getvalue().splitlines()]
    assert responses[0] == {"jsonrpc": "2.0", "id": 6, "result": {}}
    assert responses[1]["error"]["code"] == -32700
    assert responses[2]["error"]["code"] == -32600
    assert responses[2]["error"]["message"] == "request exceeds maximum size"


def test_tool_failure_is_contained_and_transport_remains_usable():
    def fail(_):
        raise RuntimeError("boom")

    server = MCPServer([ToolSpec("fails", "fail", fail)])

    failure = server.handle_request(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "fails"}}
    )

    assert failure["error"]["code"] == -32000
    assert server.handle_request({"jsonrpc": "2.0", "id": 2, "method": "ping"})["result"] == {}


def test_sse_adapter_is_optional(server):
    try:
        import fastapi  # noqa: F401
    except ImportError:
        with pytest.raises(RuntimeError, match="FastAPI"):
            server.sse_app()
    else:
        app = server.sse_app()
        assert {route.path for route in app.routes} >= {"/mcp/sse", "/mcp/messages"}
