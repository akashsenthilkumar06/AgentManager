"""Minimal MCP-style JSON-RPC 2.0 dispatcher."""
from __future__ import annotations
from typing import Any
from .state import AGENT_NAME, AGENT_VERSION
from .tools import TOOL_DEFINITIONS, invoke

def handle(payload: dict[str, Any]) -> dict[str, Any]:
    request_id = payload.get("id")
    method, params = payload.get("method"), payload.get("params", {})
    try:
        if method == "initialize":
            result = {"protocolVersion": "2024-11-05", "serverInfo": {"name": AGENT_NAME, "version": AGENT_VERSION},
                      "capabilities": {"tools": {"listChanged": False}, "resources": {}}}
        elif method == "tools/list": result = {"tools": TOOL_DEFINITIONS}
        elif method == "tools/call":
            value = invoke(params["name"], params.get("arguments", {}))
            result = {"content": [{"type": "text", "text": __import__("json").dumps(value, default=str)}], "structuredContent": value, "isError": False}
        else: raise ValueError(f"Unsupported MCP method: {method}")
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    except Exception as exc:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32000, "message": str(exc)}}
