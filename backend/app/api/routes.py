from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from fastapi import APIRouter, HTTPException, Query

from backend.app.core.models import (
    AgentChatRequest,
    AgentImportRequest,
    AgentProcessStartRequest,
    AgentUpdateRequest,
    BenchmarkRequest,
    BuildRequest,
    ConnectedWorkspace,
    ConnectWorkspaceRequest,
    ExecuteRequest,
    ManagerChatRequest,
    ToolRecord,
    utc_now,
)
from backend.app.core.openai_models import openai_model_catalog
from backend.app.dependencies import (
    architecture_agent,
    agentic_manager,
    benchmark_agent,
    conversation_agent,
    execute_registered_tool,
    import_agent,
    manager_agent,
    managed_agent_operator,
    managed_workspace,
    mock_system,
    monitoring_agent,
    openai_provider,
    runtime,
    settings,
    store,
    workspace_access,
)
from backend.app.infrastructure.openai_provider import OpenAIProviderError

router = APIRouter()


@router.get("/api/overview")
async def overview() -> dict[str, Any]:
    architecture = store.architecture()
    reconciliation = store.reconciliation_snapshot()
    return {
        "summary": architecture_agent.summary(architecture),
        "architecture": architecture.model_dump(),
        "recent_builds": [build.model_dump() for build in store.builds()[:5]],
        "recent_benchmarks": [
            run.model_dump() for run in store.benchmarks()[:5]
        ],
        "recent_conversations": [
            conversation.model_dump() for conversation in store.conversations()[:8]
        ],
        "standing_findings": [
            finding.model_dump() for finding in store.findings()[:8]
        ],
        "reconciliation": {
            "mode": "edge_triggered",
            "interval_seconds": (
                settings.reconciliation_interval_seconds
            ),
            "last_checked_at": reconciliation.get("last_checked_at"),
            "last_error": reconciliation.get("last_error"),
            "summary": reconciliation.get("summary", {}),
        },
        "openai": {
            **openai_provider.status(),
            "model_options": openai_model_catalog(),
        },
        "mcp_servers": [
            {"id": "architecture", "name": "Architecture", "status": "connected", "tools": 2},
            {"id": "workspace", "name": "Client Workspace", "status": "connected", "tools": 1},
            {"id": "developer", "name": "Developer", "status": "connected", "tools": 1},
            {"id": "validation", "name": "Validation", "status": "connected", "tools": 1},
            {"id": "monitoring", "name": "Monitoring", "status": "connected", "tools": 1},
            {"id": "runtime", "name": "Agent Runtime", "status": "connected", "tools": 5},
        ],
    }


@router.get("/api/openai/status")
async def openai_status() -> dict[str, Any]:
    return openai_provider.status()


@router.post("/api/openai/test")
async def test_openai_connection() -> dict[str, Any]:
    try:
        return await openai_provider.test_connection()
    except OpenAIProviderError as exc:
        status_code = (
            422
            if exc.status_code is None
            and not openai_provider.configured
            else 502
        )
        raise HTTPException(
            status_code=status_code,
            detail={
                "message": exc.message,
                "provider_status": openai_provider.status(),
            },
        ) from exc


@router.get("/api/findings")
async def list_findings(
    status: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    if status not in {None, "open", "observed", "resolved"}:
        raise HTTPException(
            status_code=422,
            detail="Finding status must be open, observed, or resolved",
        )
    return [
        finding.model_dump()
        for finding in store.findings(status=status)
    ]


@router.get("/api/managed-agents")
async def list_managed_agents() -> list[dict[str, Any]]:
    return [agent.model_dump() for agent in store.architecture().agents]


@router.post("/api/managed-agents/import")
async def import_managed_agent(
    request: AgentImportRequest,
) -> dict[str, Any]:
    try:
        return await import_agent.import_directory(request)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="Agent directory was not found",
        ) from exc
    except NotADirectoryError as exc:
        raise HTTPException(
            status_code=422,
            detail="Agent path must be a directory",
        ) from exc
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/api/managed-agents/{agent_id}/process")
async def managed_agent_process_status(
    agent_id: str,
) -> dict[str, Any]:
    try:
        return managed_agent_operator.status(agent_id)["process"]
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail="Managed agent not found",
        ) from exc


@router.post("/api/managed-agents/{agent_id}/process/start")
async def start_managed_agent_process(
    agent_id: str,
    request: AgentProcessStartRequest,
) -> dict[str, Any]:
    try:
        result = await managed_agent_operator.start(
            agent_id,
            request.command,
        )
        return result["process"]
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/api/managed-agents/{agent_id}/process/stop")
async def stop_managed_agent_process(
    agent_id: str,
) -> dict[str, Any]:
    try:
        return managed_agent_operator.stop(agent_id)["process"]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/api/managed-agents/discover")
async def discover_managed_agents() -> dict[str, Any]:
    architecture = store.architecture()
    agents = await architecture_agent.discover_all(architecture)
    store.update_agents(agents)
    for agent in agents:
        managed_workspace.sync(agent)
    return {
        "agents": [agent.model_dump() for agent in agents],
        "tool_count": sum(len(agent.mcp_tools) for agent in agents),
        "status": "completed",
    }


@router.post("/api/managed-agents/{agent_id}/discover")
async def discover_managed_agent(agent_id: str) -> dict[str, Any]:
    architecture = store.architecture()
    agent = next((item for item in architecture.agents if item.id == agent_id), None)
    if agent is None:
        raise HTTPException(status_code=404, detail="Managed agent not found")
    try:
        discovered = await architecture_agent.discover_agent(agent, architecture)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Could not connect to the MCP endpoint: {exc}",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    agents = [discovered if item.id == agent_id else item for item in architecture.agents]
    store.update_agents(agents)
    managed_workspace.sync(discovered)
    return discovered.model_dump()


@router.patch("/api/managed-agents/{agent_id}")
async def update_managed_agent(
    agent_id: str, request: AgentUpdateRequest
) -> dict[str, Any]:
    architecture = store.architecture()
    agent = next((item for item in architecture.agents if item.id == agent_id), None)
    if agent is None:
        raise HTTPException(status_code=404, detail="Managed agent not found")
    available_tools = {tool.name for tool in agent.mcp_tools}
    unknown_tools = set(request.enabled_tools) - available_tools
    if unknown_tools:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown agent tools: {', '.join(sorted(unknown_tools))}",
        )
    updates = request.model_dump(exclude_unset=True)
    endpoint_changed = (
        "mcp_endpoint" in updates
        and updates["mcp_endpoint"] != agent.mcp_endpoint
    )
    if endpoint_changed:
        updates.update(
            {
                "mcp_server_name": None,
                "mcp_tools": [],
                "mcp_prompts": [],
                "mcp_resources": [],
                "enabled_tools": [],
                "last_discovered_at": None,
                "status": "degraded",
            }
        )
    updated = agent.model_copy(update=updates)
    store.update_agent(updated)
    managed_workspace.sync(updated)
    return updated.model_dump()


@router.get("/api/conversations")
async def list_conversations(agent_id: str | None = None) -> list[dict[str, Any]]:
    return [
        conversation.model_dump()
        for conversation in store.conversations(agent_id=agent_id)
    ]


@router.get("/api/conversations/{conversation_id}")
async def get_conversation(conversation_id: str) -> dict[str, Any]:
    conversation = store.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation.model_dump()


@router.post("/api/conversations/message")
async def send_agent_message(request: AgentChatRequest) -> dict[str, Any]:
    try:
        conversation = await conversation_agent.respond(request)
        return conversation.model_dump()
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/api/manager/conversations")
async def list_manager_conversations(
    agent_id: str | None = None,
) -> list[dict[str, Any]]:
    return [
        conversation.model_dump()
        for conversation in store.manager_conversations(agent_id=agent_id)
    ]


@router.post("/api/manager/message")
async def send_manager_message(request: ManagerChatRequest) -> dict[str, Any]:
    try:
        return (await agentic_manager.respond(request)).model_dump()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/api/manager/conversations/{conversation_id}/apply")
async def apply_manager_changes(conversation_id: str) -> dict[str, Any]:
    try:
        return agentic_manager.apply(conversation_id).model_dump()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/api/workspace")
async def workspace_summary() -> dict[str, object]:
    return workspace_access.summary()


@router.get("/api/workspaces")
async def list_connected_workspaces() -> dict[str, Any]:
    default = {
        "id": "default",
        "name": workspace_access.root.name,
        "root_path": str(workspace_access.root),
        "agent_id": None,
        "writable": False,
        "default": True,
        **workspace_access.summary(),
    }
    connected = [
        {
            **workspace.model_dump(),
            "default": False,
            **workspace_access.summary(Path(workspace.root_path)),
        }
        for workspace in store.connected_workspaces()
        if Path(workspace.root_path).exists()
    ]
    return {"workspaces": [default, *connected]}


@router.post("/api/workspaces/connect")
async def connect_workspace(request: ConnectWorkspaceRequest) -> dict[str, Any]:
    if request.agent_id is not None:
        known_agents = {agent.id for agent in store.architecture().agents}
        if request.agent_id not in known_agents:
            raise HTTPException(status_code=422, detail="Managed agent not found")
    try:
        root = workspace_access.validate_root(Path(request.path))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Workspace path not found") from exc
    except NotADirectoryError as exc:
        raise HTTPException(status_code=422, detail="Workspace path must be a directory") from exc
    existing = next(
        (
            workspace
            for workspace in store.connected_workspaces()
            if Path(workspace.root_path).resolve() == root
        ),
        None,
    )
    now = utc_now()
    workspace = ConnectedWorkspace(
        id=existing.id if existing else f"workspace_{uuid4().hex[:10]}",
        name=request.name or root.name,
        root_path=str(root),
        agent_id=request.agent_id,
        writable=request.writable,
        created_at=existing.created_at if existing else now,
        updated_at=now,
    )
    store.upsert_connected_workspace(workspace)
    return {
        **workspace.model_dump(),
        "default": False,
        **workspace_access.summary(root),
    }


@router.get("/api/workspaces/{workspace_id}")
async def connected_workspace_summary(workspace_id: str) -> dict[str, Any]:
    root = _workspace_root(workspace_id)
    workspace = store.get_connected_workspace(workspace_id)
    metadata = (
        {"id": "default", "name": root.name, "root_path": str(root), "default": True}
        if workspace_id == "default"
        else {**workspace.model_dump(), "default": False}
    )
    return {**metadata, **workspace_access.summary(root)}


@router.get("/api/workspaces/{workspace_id}/files")
async def list_connected_workspace_files(
    workspace_id: str, path: str = Query(default="", max_length=1000)
) -> dict[str, Any]:
    try:
        return workspace_access.list_directory(path, _workspace_root(workspace_id)).model_dump()
    except (FileNotFoundError, NotADirectoryError) as exc:
        raise HTTPException(status_code=404, detail="Workspace directory not found") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/api/workspaces/{workspace_id}/file")
async def read_connected_workspace_file(
    workspace_id: str, path: str = Query(min_length=1, max_length=1000)
) -> dict[str, Any]:
    try:
        return workspace_access.read_file(path, _workspace_root(workspace_id)).model_dump()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Workspace file not found") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/api/workspace/files")
async def list_workspace_files(path: str = Query(default="", max_length=1000)) -> dict[str, Any]:
    try:
        return workspace_access.list_directory(path).model_dump()
    except (FileNotFoundError, NotADirectoryError) as exc:
        raise HTTPException(status_code=404, detail="Workspace directory not found") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/api/workspace/file")
async def read_workspace_file(path: str = Query(min_length=1, max_length=1000)) -> dict[str, Any]:
    try:
        return workspace_access.read_file(path).model_dump()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Workspace file not found") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/api/builds")
async def create_build(request: BuildRequest) -> dict[str, Any]:
    return (await manager_agent.build(request)).model_dump()


@router.post("/api/benchmarks")
async def run_benchmark(
    request: BenchmarkRequest,
) -> dict[str, Any]:
    try:
        return (await benchmark_agent.run(request.agent_id)).model_dump()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/api/benchmarks")
async def list_benchmarks(
    agent_id: str | None = None,
) -> list[dict[str, Any]]:
    return [
        run.model_dump()
        for run in store.benchmarks(agent_id=agent_id)
    ]


@router.get("/api/builds")
async def list_builds() -> list[dict[str, Any]]:
    return [build.model_dump() for build in store.builds()]


@router.get("/api/builds/{build_id}")
async def get_build(build_id: str) -> dict[str, Any]:
    for build in store.builds():
        if build.id == build_id:
            return build.model_dump()
    raise HTTPException(status_code=404, detail="Build not found")


@router.get("/api/health")
async def health() -> dict[str, Any]:
    results = await monitoring_agent.check(store.architecture())
    healthy = sum(result.status == "healthy" for result in results)
    return {
        "status": "healthy" if healthy == len(results) else "degraded",
        "healthy": healthy,
        "total": len(results),
        "results": [result.model_dump() for result in results],
        "openai": openai_provider.status(),
    }


@router.post("/api/tools/{tool_id}/execute")
async def execute_tool(tool_id: str, request: ExecuteRequest) -> dict[str, Any]:
    tool_data = store.get_tool(tool_id)
    if tool_data is None:
        raise HTTPException(status_code=404, detail="Tool not found")
    tool = ToolRecord.model_validate(tool_data)
    try:
        result = await execute_registered_tool(tool.id, request.payload)
        return {"tool": tool.name, "status": "success", "result": result}
    except (ValueError, LookupError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
@router.post("/api/reset")
async def reset_demo() -> dict[str, str]:
    store.reset()
    for path in settings.generated_dir.glob("*.py"):
        if path.name != "__init__.py":
            path.unlink()
    return {"status": "reset"}


@router.get("/mock/orders/{order_id}")
async def mock_order(order_id: str) -> dict[str, Any]:
    return await _mock_response(f"/mock/orders/{order_id}")


@router.get("/mock/invoices/{invoice_id}")
async def mock_invoice(invoice_id: str) -> dict[str, Any]:
    return await _mock_response(f"/mock/invoices/{invoice_id}")


@router.get("/mock/codebase/{repo_id}")
async def mock_codebase(repo_id: str) -> dict[str, Any]:
    return await _mock_response(f"/mock/codebase/{repo_id}")


@router.get("/mock/tickets/{ticket_id}")
async def mock_ticket(ticket_id: str) -> dict[str, Any]:
    return await _mock_response(f"/mock/tickets/{ticket_id}")


@router.get("/mock/customers/{customer_id}")
async def mock_customer(customer_id: str) -> dict[str, Any]:
    return await _mock_response(f"/mock/customers/{customer_id}")


async def _mock_response(path: str) -> dict[str, Any]:
    try:
        return await mock_system.get(path)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _workspace_root(workspace_id: str) -> Path:
    if workspace_id == "default":
        return workspace_access.root
    workspace = store.get_connected_workspace(workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Connected workspace not found")
    try:
        return workspace_access.validate_root(Path(workspace.root_path))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Workspace path not found") from exc
    except NotADirectoryError as exc:
        raise HTTPException(status_code=422, detail="Workspace path must be a directory") from exc
