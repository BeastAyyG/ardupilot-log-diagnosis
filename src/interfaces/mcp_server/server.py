"""Small read-only MCP-compatible JSON-RPC server for local integrations."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any, TextIO

ToolHandler = Callable[[dict[str, Any]], Mapping[str, Any]]


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    handler: ToolHandler


class MCPServer:
    """JSON-RPC tool server with line-based stdio and a small SSE adapter."""

    def __init__(self, tools: Iterable[ToolSpec] = (), *, max_message_bytes: int = 1_000_000):
        if max_message_bytes < 1024:
            raise ValueError("max_message_bytes must be at least 1024")
        self.max_message_bytes = int(max_message_bytes)
        self._tools: dict[str, ToolSpec] = {}
        for tool in tools:
            self.register_tool(tool)

    def register_tool(self, tool: ToolSpec) -> None:
        if not tool.name or any(character.isspace() for character in tool.name):
            raise ValueError("tool names must be non-empty and whitespace-free")
        if tool.name in self._tools:
            raise ValueError(f"duplicate tool: {tool.name}")
        self._tools[tool.name] = tool

    def _response(self, request_id: Any, result: Mapping[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": dict(result)}

    def _error(self, request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}

    def handle_request(self, request: Mapping[str, Any]) -> dict[str, Any] | None:
        """Handle one JSON-RPC request; notifications return no response."""

        if not isinstance(request, Mapping):
            return self._error(None, -32600, "invalid JSON-RPC request")
        request_id = request.get("id")

        def request_error(code: int, message: str) -> dict[str, Any] | None:
            return None if "id" not in request else self._error(request_id, code, message)

        if request.get("jsonrpc") != "2.0" or not isinstance(request.get("method"), str):
            return request_error(-32600, "invalid JSON-RPC request")
        method = request["method"]
        if method == "notifications/initialized" and "id" not in request:
            return None
        if method == "ping":
            response = self._response(request_id, {})
        elif method == "initialize":
            response = self._response(
                request_id,
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "ardupilot-log-diagnosis", "version": "1.0"},
                },
            )
        elif method == "tools/list":
            response = self._response(
                request_id,
                {"tools": [{"name": tool.name, "description": tool.description, "inputSchema": {"type": "object"}} for tool in self._tools.values()]},
            )
        elif method == "tools/call":
            params = request.get("params", {})
            if not isinstance(params, Mapping) or not isinstance(params.get("name"), str):
                return request_error(-32602, "tools/call requires params.name")
            tool = self._tools.get(params["name"])
            if tool is None:
                return request_error(-32602, f"unknown tool: {params['name']}")
            arguments = params.get("arguments", {})
            if not isinstance(arguments, Mapping):
                return request_error(-32602, "tool arguments must be an object")
            try:
                payload = dict(tool.handler(dict(arguments)))
            except Exception as exc:  # noqa: BLE001 - a tool must not terminate transport.
                return request_error(-32000, f"tool failed: {exc}")
            response = self._response(
                request_id,
                {
                    "content": [
                        {"type": "text", "text": json.dumps(payload, default=str)}
                    ],
                    "structuredContent": payload,
                },
            )
        else:
            return request_error(-32601, f"method not found: {method}")
        return None if "id" not in request else response

    def serve_stdio(self, input_stream: TextIO | None = None, output_stream: TextIO | None = None) -> None:
        """Serve newline-delimited JSON-RPC messages without shell access."""

        source = input_stream or sys.stdin
        destination = output_stream or sys.stdout
        for line in source:
            if len(line.encode("utf-8")) > self.max_message_bytes:
                response = self._error(None, -32600, "request exceeds maximum size")
            else:
                try:
                    request = json.loads(line)
                    response = self.handle_request(request) if isinstance(request, Mapping) else self._error(None, -32600, "request must be an object")
                except json.JSONDecodeError:
                    response = self._error(None, -32700, "invalid JSON")
            if response is not None:
                destination.write(json.dumps(response, separators=(",", ":")) + "\n")
                destination.flush()

    def sse_app(self) -> Any:
        """Build an optional FastAPI SSE/POST adapter when FastAPI is installed."""

        try:
            from fastapi import FastAPI, Request
            from fastapi.responses import StreamingResponse
        except ImportError as exc:
            raise RuntimeError("FastAPI is required for the SSE adapter") from exc

        app = FastAPI(title="ArduPilot Log Diagnosis MCP")

        @app.get("/mcp/sse")
        async def sse() -> StreamingResponse:
            async def events():
                yield "event: ready\ndata: {\"status\":\"ready\"}\n\n"

            return StreamingResponse(events(), media_type="text/event-stream")

        @app.post("/mcp/messages")
        async def messages(request: Request) -> dict[str, Any] | None:
            raw_body = await request.body()
            if len(raw_body) > self.max_message_bytes:
                return self._error(None, -32600, "request exceeds maximum size")
            try:
                body = json.loads(raw_body)
            except (json.JSONDecodeError, UnicodeDecodeError):
                return self._error(None, -32700, "invalid JSON")
            return self.handle_request(body) if isinstance(body, Mapping) else self._error(
                None, -32600, "request must be an object"
            )

        return app
