from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import httpx

from backend.app.core.models import AgentRecord, MCPToolCapability, ToolRecord, utc_now


@dataclass(slots=True)
class MCPDiscovery:
    server_name: str
    tools: list[MCPToolCapability] = field(default_factory=list)
    prompts: list[str] = field(default_factory=list)
    resources: list[str] = field(default_factory=list)
    features: list[str] = field(default_factory=list)
    discovered_at: str = field(default_factory=utc_now)


class ManagedAgentMCPClient:
    """Discovers a managed agent's capabilities using MCP.

    `demo://` endpoints are in-process fixtures for the local demo. HTTP(S)
    endpoints use JSON-RPC and call initialize, tools/list, prompts/list, and
    resources/list. Unsupported optional methods are treated as empty lists.
    """

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
        self.transport = transport

    async def discover(self, agent: AgentRecord, registered_tools: list[ToolRecord]) -> MCPDiscovery:
        endpoint = agent.mcp_endpoint
        if not endpoint:
            raise ValueError(f"{agent.name} has no MCP endpoint configured")
        if endpoint.startswith("demo://"):
            return self._discover_demo(agent, registered_tools)
        if endpoint.startswith(("http://", "https://")):
            return await self._discover_http(endpoint)
        raise ValueError(f"Unsupported MCP endpoint scheme for {agent.name}")

    def _discover_demo(self, agent: AgentRecord, registered_tools: list[ToolRecord]) -> MCPDiscovery:
        available = {tool.id: tool for tool in registered_tools}
        tools = [
            MCPToolCapability(
                name=available[tool_id].name,
                description=available[tool_id].description,
                input_schema=available[tool_id].input_schema,
            )
            for tool_id in agent.tool_ids
            if tool_id in available
        ]
        return MCPDiscovery(
            server_name=f"{agent.id}-mcp",
            tools=tools,
            prompts=["summarize_result"] if tools else [],
            resources=[f"agent://{agent.id}/instructions"],
            features=list(agent.features),
        )

    async def _discover_http(self, endpoint: str) -> MCPDiscovery:
        async with httpx.AsyncClient(
            timeout=12.0, transport=self.transport
        ) as client:
            initialized = await self._call(client, endpoint, 1, "initialize", {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "agentic-ai-manager", "version": "0.1.0"},
            })
            tools_result = await self._call(client, endpoint, 2, "tools/list", {})
            prompts_result = await self._optional_call(client, endpoint, 3, "prompts/list")
            resources_result = await self._optional_call(client, endpoint, 4, "resources/list")

        tools = [
            MCPToolCapability(
                name=str(item.get("name", "unnamed_tool")),
                description=str(item.get("description", "")),
                input_schema=item.get("inputSchema", {}),
            )
            for item in tools_result.get("tools", [])
            if isinstance(item, dict)
        ]
        prompts = [str(item.get("name")) for item in prompts_result.get("prompts", []) if isinstance(item, dict) and item.get("name")]
        resources = [str(item.get("uri")) for item in resources_result.get("resources", []) if isinstance(item, dict) and item.get("uri")]
        server_info = initialized.get("serverInfo", {})
        return MCPDiscovery(
            server_name=str(server_info.get("name", endpoint)),
            tools=tools,
            prompts=prompts,
            resources=resources,
            features=[tool.description or tool.name for tool in tools],
        )

    async def call_tool(
        self,
        endpoint: str,
        name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        if not endpoint.startswith(("http://", "https://")):
            raise ValueError("Live MCP tool calls require an HTTP(S) endpoint")
        async with httpx.AsyncClient(
            timeout=20.0, transport=self.transport
        ) as client:
            result = await self._call(
                client,
                endpoint,
                20,
                "tools/call",
                {"name": name, "arguments": arguments},
            )
        if result.get("isError"):
            raise ValueError(self._content_text(result) or f"MCP tool {name} failed")
        text = self._content_text(result)
        if not text:
            return {"content": result}
        try:
            parsed = json.loads(text)
        except ValueError:
            return {"content": text}
        return parsed if isinstance(parsed, dict) else {"content": parsed}

    @staticmethod
    async def _call(
        client: httpx.AsyncClient,
        endpoint: str,
        request_id: int,
        method: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        response = await client.post(endpoint, json={"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        response.raise_for_status()
        payload = response.json()
        if "error" in payload:
            error = payload["error"]
            message = (
                error.get("message", f"MCP {method} failed")
                if isinstance(error, dict)
                else error
            )
            raise ValueError(str(message))
        return payload.get("result", {})

    async def _optional_call(self, client: httpx.AsyncClient, endpoint: str, request_id: int, method: str) -> dict[str, Any]:
        try:
            return await self._call(client, endpoint, request_id, method, {})
        except (httpx.HTTPError, ValueError, KeyError):
            return {}

    @staticmethod
    def _content_text(result: dict[str, Any]) -> str:
        return "\n".join(
            str(item.get("text", ""))
            for item in result.get("content", [])
            if isinstance(item, dict)
            and item.get("type") == "text"
            and item.get("text") is not None
        ).strip()
