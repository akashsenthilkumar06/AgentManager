from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from backend.app.core.models import (
    AgentChatRequest,
    AgentUpdateRequest,
    BuildRequest,
    ExecuteRequest,
    ManagerChatRequest,
    ToolRecord,
)
from backend.app.dependencies import (
    architecture_agent,
    agentic_manager,
    conversation_agent,
    manager_agent,
    mock_system,
    monitoring_agent,
    runtime,
    settings,
    store,
    workspace_access,
)


router = APIRouter()


@router.get("/api/overview")
async def overview() -> dict[str, Any]:
    architecture = store.architecture()
    return {
        "summary": architecture_agent.summary(architecture),
        "architecture": architecture.model_dump(),
        "recent_builds": [build.model_dump() for build in store.builds()[:5]],
        "recent_conversations": [
            conversation.model_dump() for conversation in store.conversations()[:8]
        ],
        "mcp_servers": [
            {"id": "architecture", "name": "Architecture", "status": "connected", "tools": 2},
            {"id": "workspace", "name": "Client Workspace", "status": "connected", "tools": 1},
            {"id": "developer", "name": "Developer", "status": "connected", "tools": 1},
            {"id": "validation", "name": "Validation", "status": "connected", "tools": 1},
            {"id": "monitoring", "name": "Monitoring", "status": "connected", "tools": 1},
        ],
    }


@router.get("/api/managed-agents")
async def list_managed_agents() -> list[dict[str, Any]]:
    return [agent.model_dump() for agent in store.architecture().agents]


@router.post("/api/managed-agents/discover")
async def discover_managed_agents() -> dict[str, Any]:
    architecture = store.architecture()
    agents = await architecture_agent.discover_all(architecture)
    store.update_agents(agents)
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
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    agents = [discovered if item.id == agent_id else item for item in architecture.agents]
    store.update_agents(agents)
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
    updated = agent.model_copy(update=request.model_dump())
    store.update_agent(updated)
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
    }


@router.post("/api/tools/{tool_id}/execute")
async def execute_tool(tool_id: str, request: ExecuteRequest) -> dict[str, Any]:
    tool_data = store.get_tool(tool_id)
    if tool_data is None:
        raise HTTPException(status_code=404, detail="Tool not found")
    tool = ToolRecord.model_validate(tool_data)
    try:
        if tool.generated and tool.source_file:
            result = await runtime.execute_file(tool.source_file, request.payload, mock_system.get)
        else:
            result = await _execute_existing(tool.operation, request.payload)
        return {"tool": tool.name, "status": "success", "result": result}
    except (ValueError, LookupError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


async def _execute_existing(operation: str | None, payload: dict[str, Any]) -> dict[str, Any]:
    if operation == "lookup_order":
        return await mock_system.get("/mock/orders/" + str(payload.get("order_id", "")).upper())
    if operation == "track_shipment":
        return await mock_system.get("/mock/shipments/by-order/" + str(payload.get("order_id", "")).upper())
    if operation == "check_inventory":
        return await mock_system.get("/mock/inventory/" + str(payload.get("sku", "")).upper())
    raise ValueError("Tool has no executable operation")


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


@router.get("/mock/shipments/by-order/{order_id}")
async def mock_shipment(order_id: str) -> dict[str, Any]:
    return await _mock_response(f"/mock/shipments/by-order/{order_id}")


@router.get("/mock/inventory/{sku}")
async def mock_inventory(sku: str) -> dict[str, Any]:
    return await _mock_response(f"/mock/inventory/{sku}")


@router.get("/mock/customers/{customer_id}")
async def mock_customer(customer_id: str) -> dict[str, Any]:
    return await _mock_response(f"/mock/customers/{customer_id}")


async def _mock_response(path: str) -> dict[str, Any]:
    try:
        return await mock_system.get(path)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
