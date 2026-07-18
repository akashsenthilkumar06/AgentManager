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
        {"name": "workspace.inspect", "description": "Inspect the selected managed agent's editable local workspace.", "inputSchema": {"type": "object", "required": ["agent_id"], "properties": {"agent_id": {"type": "string"}, "query": {"type": "string"}}}},
        {
            "name": "workspace.write_file",
            "description": "Create or replace one supported source/text file inside an imported agent workspace. Requires explicit Auto permission.",
            "inputSchema": {
                "type": "object",
                "required": [
                    "agent_id",
                    "path",
                    "content",
                    "permission_mode",
                ],
                "properties": {
                    "agent_id": {"type": "string"},
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "permission_mode": {
                        "type": "string",
                        "enum": ["auto"],
                    },
                },
            },
        },
        {
            "name": "workspace.run_python_file",
            "description": "Run one Python file inside an imported agent workspace without a shell or control-plane secrets. Requires explicit Auto permission.",
            "inputSchema": {
                "type": "object",
                "required": [
                    "agent_id",
                    "path",
                    "permission_mode",
                ],
                "properties": {
                    "agent_id": {"type": "string"},
                    "path": {"type": "string"},
                    "permission_mode": {
                        "type": "string",
                        "enum": ["auto"],
                    },
                },
            },
        },
    ],
    "developer": [
        {"name": "developer.generate", "description": "Generate a constrained tool from a natural-language request.", "inputSchema": {"type": "object", "required": ["prompt"], "properties": {"prompt": {"type": "string"}}}},
        {
            "name": "developer.propose_change",
            "description": "Prepare one bounded, reversible instruction change for a managed agent.",
            "inputSchema": {
                "type": "object",
                "required": [
                    "objective",
                    "current_instructions",
                    "instructions_append",
                ],
                "properties": {
                    "objective": {"type": "string"},
                    "current_instructions": {"type": "string"},
                    "instructions_append": {"type": "string"},
                },
            },
        },
    ],
    "validation": [
        {"name": "validation.check", "description": "Validate generated source and its declared tool contract.", "inputSchema": {"type": "object", "required": ["source", "tool"], "properties": {"source": {"type": "string"}, "tool": {"type": "object"}}}},
        {
            "name": "validation.evaluate",
            "description": "Evaluate a Manager instruction change, workspace operation, or runtime operation from its recorded action evidence.",
            "inputSchema": {
                "type": "object",
                "required": [
                    "objective",
                    "operation_kind",
                    "changes",
                    "actions",
                ],
                "properties": {
                    "objective": {"type": "string"},
                    "operation_kind": {
                        "type": ["string", "null"],
                    },
                    "changes": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                    "actions": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                },
            },
        },
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
        content = managed_workspace.inspect(
            agent,
            query=str(arguments.get("query", "")),
        )
    elif server_id == "workspace" and name in {
        "workspace.write_file",
        "workspace.run_python_file",
    }:
        if arguments.get("permission_mode") != "auto":
            raise PermissionError(
                "Workspace file operations require Auto permission"
            )
        agent_id = str(arguments.get("agent_id", ""))
        agent = next(
            (item for item in architecture.agents if item.id == agent_id),
            None,
        )
        if agent is None:
            raise ValueError("Managed agent not found")
        path = str(arguments.get("path", ""))
        if name == "workspace.write_file":
            content = managed_workspace.write_file(
                agent,
                path,
                str(arguments.get("content", "")),
            )
        else:
            content = await managed_workspace.run_python_file(
                agent,
                path,
            )
    elif server_id == "developer" and name == "developer.generate":
        prompt = str(arguments.get("prompt", ""))
        artifact = developer_agent.generate(prompt, architecture_agent.search(prompt, architecture))
        content = {"tool": artifact.tool.model_dump(), "source": artifact.source, "plan": artifact.plan}
    elif server_id == "developer" and name == "developer.propose_change":
        content = developer_agent.propose_instruction_change(
            str(arguments.get("objective", "")),
            str(arguments.get("current_instructions", "")),
            str(arguments.get("instructions_append", "")),
        )
    elif server_id == "validation" and name == "validation.check":
        tool = ToolRecord.model_validate(arguments["tool"])
        checks = await validation_agent.validate(str(arguments["source"]), tool, {endpoint.id for endpoint in architecture.endpoints})
        content = [check.model_dump() for check in checks]
    elif server_id == "validation" and name == "validation.evaluate":
        changes = arguments.get("changes", [])
        actions = arguments.get("actions", [])
        if not isinstance(changes, list) or not isinstance(actions, list):
            raise ValueError("Validation changes and actions must be arrays")
        evaluation = validation_agent.evaluate_manager_operation(
            (
                str(arguments["operation_kind"])
                if arguments.get("operation_kind") is not None
                else None
            ),
            [
                item
                for item in changes
                if isinstance(item, dict)
            ],
            [
                item
                for item in actions
                if isinstance(item, dict)
            ],
        )
        content = {"evaluation": evaluation.model_dump()}
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
