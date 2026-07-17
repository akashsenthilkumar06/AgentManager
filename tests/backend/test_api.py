"""End-to-end backend API and agent pipeline tests."""

from __future__ import annotations


def test_overview_starts_with_demo_architecture(client):
    response = client.get("/api/overview")

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["counts"] == {
        "agents": 3,
        "tools": 3,
        "endpoints": 4,
        "data_sources": 3,
    }
    assert len(body["mcp_servers"]) == 5


def test_backend_is_api_only_and_allows_react_dev_origin(client):
    root = client.get("/")
    assert root.status_code == 200
    assert root.json()["service"] == "Agentic AI Manager API"

    preflight = client.options(
        "/api/overview",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"


def test_order_capability_builds_validates_registers_and_executes(client):
    response = client.post(
        "/api/builds",
        json={
            "prompt": "Build a tool that checks an order shipment status and summarizes any delays.",
            "deploy": True,
        },
    )

    assert response.status_code == 200
    build = response.json()
    assert build["status"] == "completed"
    assert build["tool"]["id"] == "order_status_summary"
    assert {"orders-api", "shipments-api"}.issubset(build["tool"]["endpoint_ids"])
    assert all(check["status"] == "passed" for check in build["validations"])
    assert all(stage["status"] == "passed" for stage in build["stages"])
    assert any(match["path"] == "orders.py" for match in build["workspace_files"])
    assert build["plan"]["workspace_files"] == build["workspace_files"]

    execution = client.post(
        "/api/tools/order_status_summary/execute",
        json={"payload": {"order_id": "ORD-1042"}},
    )
    assert execution.status_code == 200
    result = execution.json()["result"]
    assert result["delayed"] is True
    assert result["delay_hours"] == 14
    assert "Weather delay" in result["summary"]

    health = client.get("/api/health").json()
    generated = next(item for item in health["results"] if item["id"] == "order_status_summary")
    assert generated["status"] == "healthy"
    assert "continuous probe" in generated["message"]


def test_inventory_request_routes_to_inventory_tool(client):
    response = client.post(
        "/api/builds",
        json={"prompt": "Create an inventory availability and stockout risk tool for each SKU."},
    )

    build = response.json()
    assert build["status"] == "completed"
    assert build["tool"]["id"] == "inventory_risk_summary"
    assert build["plan"]["routing"]["intent"] == "inventory_risk"

    execution = client.post(
        "/api/tools/inventory_risk_summary/execute",
        json={"payload": {"sku": "SKU-BLU-07"}},
    )
    assert execution.status_code == 200
    assert execution.json()["result"]["risk"] == "out_of_stock"


def test_mcp_gateway_lists_and_calls_architecture_tools(client):
    listed = client.post(
        "/mcp/architecture",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    assert listed.status_code == 200
    assert {tool["name"] for tool in listed.json()["result"]["tools"]} == {
        "architecture.snapshot",
        "architecture.search",
    }

    called = client.post(
        "/mcp/architecture",
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "architecture.search", "arguments": {"prompt": "shipment delay status"}},
        },
    )
    assert called.status_code == 200
    text = called.json()["result"]["content"][0]["text"]
    assert "shipments-api" in text


def test_manager_discovers_managed_agent_mcp_capabilities(client):
    response = client.post("/api/managed-agents/discover", json={})
    assert response.status_code == 200
    body = response.json()
    assert body["tool_count"] == 3
    assert all(agent["mcp_server_name"] for agent in body["agents"])
    assert {tool["name"] for agent in body["agents"] for tool in agent["mcp_tools"]} == {
        "lookup_order",
        "track_shipment",
        "check_inventory",
    }


def test_legacy_agent_state_backfills_mcp_configuration(client):
    import backend.app.dependencies as dependencies

    state = dependencies.store.read()
    for agent in state["architecture"]["agents"]:
        agent.pop("mcp_endpoint", None)
        agent.pop("features", None)
    dependencies.store._write(state)

    discovered = client.post("/api/managed-agents/discover", json={}).json()
    assert discovered["tool_count"] == 3
    assert all(agent["mcp_endpoint"].startswith("demo://") for agent in discovered["agents"])


def test_workspace_access_is_read_only_scoped_and_hides_secrets(client):
    listing = client.get("/api/workspace/files")
    assert listing.status_code == 200
    names = {entry["name"] for entry in listing.json()["entries"]}
    assert "orders.py" in names
    assert ".env" not in names

    preview = client.get("/api/workspace/file", params={"path": "orders.py"})
    assert preview.status_code == 200
    assert "lookup_order" in preview.json()["content"]

    traversal = client.get("/api/workspace/file", params={"path": "../outside.txt"})
    assert traversal.status_code == 403


def test_agent_conversation_imports_context_runs_tool_and_verifies_output(client):
    response = client.post(
        "/api/conversations/message",
        json={
            "agent_id": "logistics-agent",
            "message": "Where is ORD-1042 and is it delayed?",
            "context_mode": "full",
        },
    )

    assert response.status_code == 200
    conversation = response.json()
    assert conversation["agent_id"] == "logistics-agent"
    answer = conversation["messages"][-1]
    assert "14 hours" in answer["content"]
    assert answer["tool_calls"][0]["tool_name"] == "track_shipment"
    assert answer["verification"]["status"] == "verified"
    assert answer["verification"]["confidence"] > 0.9
    assert "Recent agent conversation history" in answer["context_used"]

    listed = client.get("/api/conversations", params={"agent_id": "logistics-agent"})
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == conversation["id"]


def test_managed_agent_configuration_can_be_edited_and_persisted(client):
    current = client.get("/api/managed-agents").json()[0]
    response = client.patch(
        f"/api/managed-agents/{current['id']}",
        json={
            "name": "Premium Order Agent",
            "description": "Resolves premium customer order questions with current evidence.",
            "owner": "Premium Support",
            "instructions": "Use current order data, state uncertainty clearly, and escalate unresolved fulfillment exceptions.",
            "features": ["Order lookup", "Premium support"],
            "response_style": "concise",
            "tool_policy": "approval",
            "enabled_tools": ["lookup_order"],
            "verification_mode": "strict",
            "memory_enabled": False,
        },
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["name"] == "Premium Order Agent"
    assert updated["tool_policy"] == "approval"
    assert updated["memory_enabled"] is False
    persisted = client.get("/api/managed-agents").json()[0]
    assert persisted["instructions"].startswith("Use current order data")


def test_manager_chat_selects_tools_stages_and_applies_agent_change(client):
    response = client.post(
        "/api/manager/message",
        json={
            "agent_id": "logistics-agent",
            "message": "Make the agent explain whether a proposed delivery promise is supported by carrier evidence.",
            "autonomy": "review",
        },
    )

    assert response.status_code == 200
    conversation = response.json()
    manager_message = conversation["messages"][-1]
    assert {action["tool"] for action in manager_message["actions"]} == {
        "architecture.search",
        "workspace.inspect",
        "developer.propose_change",
        "validation.evaluate",
    }
    assert manager_message["changes"][0]["status"] == "pending"
    assert manager_message["evaluation"]["status"] == "passed"
    assert manager_message["provider"] == "local:deterministic"

    applied = client.post(
        f"/api/manager/conversations/{conversation['id']}/apply"
    )
    assert applied.status_code == 200
    assert applied.json()["messages"][-2]["changes"][0]["status"] == "applied"
    agent = next(
        item
        for item in client.get("/api/managed-agents").json()
        if item["id"] == "logistics-agent"
    )
    assert "delivery promise" in agent["instructions"]

    import backend.app.dependencies as dependencies

    instructions_file = (
        dependencies.store.path.parent
        / "managed_workspaces"
        / "logistics-agent"
        / "instructions.md"
    )
    assert instructions_file.exists()
    assert "delivery promise" in instructions_file.read_text(encoding="utf-8")


def test_manager_auto_mode_applies_validated_change_immediately(client):
    response = client.post(
        "/api/manager/message",
        json={
            "agent_id": "catalog-agent",
            "message": "Always explain reservation impact when stock is low.",
            "autonomy": "auto",
        },
    )

    assert response.status_code == 200
    change = response.json()["messages"][-1]["changes"][0]
    assert change["status"] == "applied"
    agent = next(
        item
        for item in client.get("/api/managed-agents").json()
        if item["id"] == "catalog-agent"
    )
    assert "reservation impact" in agent["instructions"]


def test_build_prompt_is_validated(client):
    response = client.post("/api/builds", json={"prompt": "short"})
    assert response.status_code == 422
