from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.app.core.models import JsonRpcRequest, ToolRecord
from backend.app.dependencies import (
    architecture_agent,
    developer_agent,
    managed_agent_operator,
    managed_workspace,
    monitoring_agent,
    store,
    validation_agent,
)


router = APIRouter()

MCP_TOOLS = {
    "architecture": [
        {"name": "architecture.snapshot", "description": "Return the indexed agent architecture.", "inputSchema": {"type": "object", "properties": {}}},
        {"name": "architecture.search", "description": "Find reusable components relevant to a request.", "inputSchema": {"type": "object", "required": ["prompt"], "properties": {"prompt": {"type": "string"}}}},
    ],
    "workspace": [
        {"name": "workspace.inspect", "description": "Inspect the selected managed agent's editable local workspace.", "inputSchema": {"type": "object", "required": ["agent_id"], "properties": {"agent_id": {"type": "string"}}}},
    ],
    "developer": [
        {"name": "developer.generate", "description": "Generate a constrained tool from a natural-language request.", "inputSchema": {"type": "object", "required": ["prompt"], "properties": {"prompt": {"type": "string"}}}},
    ],
    "validation": [
        {"name": "validation.check", "description": "Validate generated source and its declared tool contract.", "inputSchema": {"type": "object", "required": ["source", "tool"], "properties": {"source": {"type": "string"}, "tool": {"type": "object"}}}},
    ],
    "monitoring": [
        {"name": "monitoring.health", "description": "Probe registered tools and endpoints.", "inputSchema": {"type": "object", "properties": {}}},
    ],
    "runtime": [
        {
            "name": "runtime.status",
            "description": "Return the selected managed agent's process, workspace, endpoint, and discovered-tool status.",
            "inputSchema": {
                "type": "object",
                "required": ["agent_id"],
                "properties": {"agent_id": {"type": "string"}},
            },
        },
        {
            "name": "runtime.start",
            "description": "Start an imported agent using only its saved run command, then wait for and discover its MCP endpoint.",
            "inputSchema": {
                "type": "object",
                "required": ["agent_id"],
                "properties": {"agent_id": {"type": "string"}},
            },
        },
        {
            "name": "runtime.stop",
            "description": "Stop the selected imported agent's managed process group.",
            "inputSchema": {
                "type": "object",
                "required": ["agent_id"],
                "properties": {"agent_id": {"type": "string"}},
            },
        },
        {
            "name": "runtime.discover",
            "description": "Connect to the selected agent's MCP endpoint and refresh its real advertised tools.",
            "inputSchema": {
                "type": "object",
                "required": ["agent_id"],
                "properties": {"agent_id": {"type": "string"}},
            },
        },
        {
            "name": "runtime.call_tool",
            "description": "Call one enabled tool exposed by the selected managed agent and return its real output.",
            "inputSchema": {
                "type": "object",
                "required": ["agent_id", "tool_name", "arguments"],
                "properties": {
                    "agent_id": {"type": "string"},
                    "tool_name": {"type": "string"},
                    "arguments": {
                        "type": "object",
                        "additionalProperties": True,
                    },
                },
            },
        },
    ],
}


@router.post("/mcp/{server_id}")
async def mcp_gateway(server_id: str, request: JsonRpcRequest) -> JSONResponse:
    if server_id not in MCP_TOOLS:
        return _rpc_error(request.id, -32601, "Unknown MCP server")
    try:
        if request.method == "initialize":
            result: Any = {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": f"agent-manager-{server_id}", "version": "0.1.0"},
            }
        elif request.method == "tools/list":
            result = {"tools": MCP_TOOLS[server_id]}
        elif request.method == "tools/call":
            result = await _mcp_call(server_id, request.params)
        else:
            return _rpc_error(request.id, -32601, f"Unsupported method: {request.method}")
        return JSONResponse({"jsonrpc": "2.0", "id": request.id, "result": result})
    except Exception as exc:
        return _rpc_error(request.id, -32000, str(exc))


async def _mcp_call(server_id: str, params: dict[str, Any]) -> dict[str, Any]:
    name = params.get("name")
    arguments = params.get("arguments", {})
    architecture = store.architecture()
    if server_id == "architecture" and name == "architecture.snapshot":
        content = architecture.model_dump()
    elif server_id == "architecture" and name == "architecture.search":
        content = [item.model_dump() for item in architecture_agent.search(str(arguments.get("prompt", "")), architecture)]
    elif server_id == "workspace" and name == "workspace.inspect":
        agent_id = str(arguments.get("agent_id", ""))
        agent = next((item for item in architecture.agents if item.id == agent_id), None)
        if agent is None:
            raise ValueError("Managed agent not found")
        content = managed_workspace.inspect(agent)
    elif server_id == "developer" and name == "developer.generate":
        prompt = str(arguments.get("prompt", ""))
        artifact = developer_agent.generate(prompt, architecture_agent.search(prompt, architecture))
        content = {"tool": artifact.tool.model_dump(), "source": artifact.source, "plan": artifact.plan}
    elif server_id == "validation" and name == "validation.check":
        tool = ToolRecord.model_validate(arguments["tool"])
        checks = await validation_agent.validate(str(arguments["source"]), tool, {endpoint.id for endpoint in architecture.endpoints})
        content = [check.model_dump() for check in checks]
    elif server_id == "monitoring" and name == "monitoring.health":
        content = [item.model_dump() for item in await monitoring_agent.check(architecture)]
    elif server_id == "runtime" and name == "runtime.status":
        content = managed_agent_operator.status(
            str(arguments.get("agent_id", ""))
        )
    elif server_id == "runtime" and name == "runtime.start":
        content = await managed_agent_operator.start(
            str(arguments.get("agent_id", ""))
        )
    elif server_id == "runtime" and name == "runtime.stop":
        content = managed_agent_operator.stop(
            str(arguments.get("agent_id", ""))
        )
    elif server_id == "runtime" and name == "runtime.discover":
        content = await managed_agent_operator.discover(
            str(arguments.get("agent_id", ""))
        )
    elif server_id == "runtime" and name == "runtime.call_tool":
        tool_arguments = arguments.get("arguments", {})
        if not isinstance(tool_arguments, dict):
            raise ValueError("Tool arguments must be an object")
        content = await managed_agent_operator.call_tool(
            str(arguments.get("agent_id", "")),
            str(arguments.get("tool_name", "")),
            tool_arguments,
        )
    else:
        raise ValueError(f"Unknown tool {name!r} for server {server_id!r}")
    text = content if isinstance(content, str) else json.dumps(content, indent=2)
    return {"content": [{"type": "text", "text": text}], "isError": False}


def _rpc_error(request_id: str | int | None, code: int, message: str) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}})
