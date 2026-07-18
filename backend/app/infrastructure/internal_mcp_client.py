"""JSON-RPC client used by the Manager to call its real internal MCP gateway."""

from __future__ import annotations

import json
from typing import Any

import httpx


class InternalMCPClient:
    """Calls Manager specialist servers through the same ASGI MCP routes."""

    def __init__(self):
        self.transport: httpx.AsyncBaseTransport | None = None
        self._tools: dict[str, set[str]] = {}
        self._request_id = 1000

    def bind(self, app: Any) -> None:
        self.transport = httpx.ASGITransport(app=app)
        self._tools.clear()

    async def call_tool(
        self,
        server_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        if self.transport is None:
            raise RuntimeError(
                "The internal MCP client is not bound to the application"
            )
        handshake_performed = False
        async with httpx.AsyncClient(
            transport=self.transport,
            base_url="http://agent-manager.internal",
            timeout=30.0,
        ) as client:
            if server_id not in self._tools:
                handshake_performed = True
                await self._rpc(
                    client,
                    server_id,
                    "initialize",
                    {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {
                            "name": "agentic-manager",
                            "version": "0.1.0",
                        },
                    },
                )
                listing = await self._rpc(
                    client,
                    server_id,
                    "tools/list",
                    {},
                )
                self._tools[server_id] = {
                    str(tool.get("name"))
                    for tool in listing.get("tools", [])
                    if isinstance(tool, dict) and tool.get("name")
                }
            if tool_name not in self._tools[server_id]:
                raise ValueError(
                    f"MCP server {server_id!r} does not advertise "
                    f"{tool_name!r}"
                )
            result = await self._rpc(
                client,
                server_id,
                "tools/call",
                {
                    "name": tool_name,
                    "arguments": arguments,
                },
            )
        if result.get("isError"):
            raise ValueError(
                self._content_text(result)
                or f"MCP tool {tool_name} failed"
            )
        text = self._content_text(result)
        if not text:
            return {"content": result}
        try:
            parsed = json.loads(text)
        except ValueError:
            parsed_result: dict[str, Any] = {"content": text}
        else:
            parsed_result = (
                parsed
                if isinstance(parsed, dict)
                else {"content": parsed}
            )
        parsed_result["_manager_mcp"] = {
            "transport": "ASGI",
            "endpoint": f"/mcp/{server_id}",
            "protocol": "JSON-RPC 2.0",
            "handshake": (
                ["initialize", "tools/list"]
                if handshake_performed
                else []
            ),
            "call": "tools/call",
            "advertised_tool": tool_name,
        }
        return parsed_result

    async def _rpc(
        self,
        client: httpx.AsyncClient,
        server_id: str,
        method: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        self._request_id += 1
        response = await client.post(
            f"/mcp/{server_id}",
            json={
                "jsonrpc": "2.0",
                "id": self._request_id,
                "method": method,
                "params": params,
            },
        )
        response.raise_for_status()
        payload = response.json()
        if "error" in payload:
            error = payload["error"]
            message = (
                error.get("message", f"MCP {method} failed")
                if isinstance(error, dict)
                else str(error)
            )
            raise ValueError(str(message))
        result = payload.get("result", {})
        if not isinstance(result, dict):
            raise ValueError(
                f"MCP {method} returned a non-object result"
            )
        return result

    @staticmethod
    def _content_text(result: dict[str, Any]) -> str:
        return "\n".join(
            str(item.get("text", ""))
            for item in result.get("content", [])
            if isinstance(item, dict)
            and item.get("type") == "text"
        ).strip()
