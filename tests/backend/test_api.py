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
            "prompt": "Build a finance tool that checks invoice status and summarizes payment risk.",
            "deploy": True,
        },
    )

    assert response.status_code == 200
    build = response.json()
    assert build["status"] == "completed"
    assert build["tool"]["id"] == "invoice_status_summary"
    assert {"invoices-api", "customers-api"}.issubset(build["tool"]["endpoint_ids"])
    assert all(check["status"] == "passed" for check in build["validations"])
    assert all(stage["status"] == "passed" for stage in build["stages"])
    assert build["workspace_files"]
    assert build["plan"]["workspace_files"] == build["workspace_files"]

    execution = client.post(
        "/api/tools/invoice_status_summary/execute",
        json={"payload": {"invoice_id": "INV-2048"}},
    )
    assert execution.status_code == 200
    result = execution.json()["result"]
    assert result["past_due"] is True
    assert result["status"] == "past_due"
    assert "due date" in result["summary"].lower()

    health = client.get("/api/health").json()
    generated = next(item for item in health["results"] if item["id"] == "invoice_status_summary")
    assert generated["status"] == "healthy"
    assert "continuous probe" in generated["message"]


def test_inventory_request_routes_to_inventory_tool(client):
    response = client.post(
        "/api/builds",
        json={"prompt": "Create a code review tool that checks repository health and release risk."},
    )

    build = response.json()
    assert build["status"] == "completed"
    assert build["tool"]["id"] == "code_health_summary"
    assert build["plan"]["routing"]["intent"] == "code_review"

    execution = client.post(
        "/api/tools/code_health_summary/execute",
        json={"payload": {"repo_id": "REPO-1"}},
    )
    assert execution.status_code == 200
    assert execution.json()["result"]["high_risk"] is True


def test_build_reuses_existing_fleet_tool_and_attaches_it_to_target(client):
    before = client.get("/api/overview").json()["summary"]["counts"]["tools"]
    response = client.post(
        "/api/builds",
        json={
            "prompt": (
                "Create a tool that checks inventory availability for a SKU"
            ),
            "agent_id": "order-support-agent",
            "deploy": True,
        },
    )

    assert response.status_code == 200
    build = response.json()
    assert build["status"] == "completed"
    assert build["decision"] == "attach"
    assert build["matched_tool_id"] == "check-inventory"
    assert build["attached_agent_ids"] == ["order-support-agent"]
    assert build["source_code"] is None
    assert build["plan"]["fleet_preflight"]["relation"] == "equivalent"
    assert build["plan"]["fleet_preflight"]["source_agent_ids"] == [
        "catalog-agent"
    ]
    assert "avoids a duplicate" in build["decision_reason"]
    assert client.get("/api/overview").json()["summary"]["counts"]["tools"] == before

    target = next(
        agent
        for agent in client.get("/api/managed-agents").json()
        if agent["id"] == "order-support-agent"
    )
    assert "check-inventory" in target["tool_ids"]
    assert "check_inventory" in target["enabled_tools"]
    attached = next(
        tool
        for tool in target["attached_tools"]
        if tool["name"] == "check_inventory"
    )
    assert attached["provider"] == "manager_runtime"
    assert attached["tool_id"] == "check-inventory"


def test_repeat_build_attaches_once_then_reuses_without_regeneration(client):
    prompt = (
        "Build a tool that checks an order shipment status and summarizes "
        "any delays."
    )
    first = client.post(
        "/api/builds",
        json={
            "prompt": prompt,
            "agent_id": "logistics-agent",
            "deploy": True,
        },
    ).json()
    assert first["decision"] == "build"
    assert first["attached_agent_ids"] == ["logistics-agent"]

    second = client.post(
        "/api/builds",
        json={
            "prompt": prompt,
            "agent_id": "order-support-agent",
            "deploy": True,
        },
    ).json()
    assert second["decision"] == "attach"
    assert second["matched_tool_id"] == "order_status_summary"
    assert second["source_code"] is None
    assert second["attached_agent_ids"] == ["order-support-agent"]

    third = client.post(
        "/api/builds",
        json={
            "prompt": prompt,
            "agent_id": "order-support-agent",
            "deploy": True,
        },
    ).json()
    assert third["decision"] == "reuse"
    assert third["attached_agent_ids"] == []
    assert "already has" in third["decision_reason"]

    tools = client.get("/api/overview").json()["architecture"]["tools"]
    assert [tool["id"] for tool in tools].count("order_status_summary") == 1

    rediscovered = client.post(
        "/api/managed-agents/order-support-agent/discover",
        json={},
    ).json()
    discovered_names = [
        tool["name"] for tool in rediscovered["mcp_tools"]
    ]
    assert discovered_names.count("order_status_summary") == 1
    assert "order_status_summary" in rediscovered["enabled_tools"]

    import backend.app.dependencies as dependencies

    tools_file = (
        dependencies.store.path.parent
        / "managed_workspaces"
        / "order-support-agent"
        / "tools.json"
    )
    contents = tools_file.read_text(encoding="utf-8")
    assert '"attached_tools"' in contents
    assert '"order_status_summary"' in contents


def test_build_blocks_target_tool_contract_conflict_without_registering(client):
    import backend.app.dependencies as dependencies
    from backend.app.core.models import MCPToolCapability

    architecture = dependencies.store.architecture()
    target = next(
        agent
        for agent in architecture.agents
        if agent.id == "order-support-agent"
    )
    conflicting = MCPToolCapability(
        name="order_status_summary",
        description="An unrelated pre-existing target capability.",
        input_schema={
            "type": "object",
            "required": ["sku"],
            "properties": {"sku": {"type": "string"}},
        },
        provider="agent_mcp",
        provider_endpoint="https://existing-agent.invalid/mcp",
    )
    dependencies.store.update_agent(
        target.model_copy(
            update={
                "attached_tools": [conflicting],
                "mcp_tools": [conflicting],
                "enabled_tools": ["order_status_summary"],
            }
        )
    )

    response = client.post(
        "/api/builds",
        json={
            "prompt": (
                "Build a tool that checks an order shipment status and "
                "summarizes any delays."
            ),
            "agent_id": "order-support-agent",
            "deploy": True,
        },
    )

    assert response.status_code == 200
    build = response.json()
    assert build["status"] == "failed"
    assert build["decision"] == "conflict"
    assert "different input contract" in build["decision_reason"]
    assert build["stages"][1]["status"] == "failed"
    assert all(
        tool["id"] != "order_status_summary"
        for tool in client.get("/api/overview").json()["architecture"]["tools"]
    )
    assert not (
        dependencies.runtime.generated_dir
        / "order_status_summary.py"
    ).exists()


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
            "params": {"name": "architecture.search", "arguments": {"prompt": "invoice payment status"}},
        },
    )
    assert called.status_code == 200
    text = called.json()["result"]["content"][0]["text"]
    assert "invoices-api" in text


def test_manager_discovers_managed_agent_mcp_capabilities(client):
    response = client.post("/api/managed-agents/discover", json={})
    assert response.status_code == 200
    body = response.json()
    assert body["tool_count"] == 3
    assert all(agent["mcp_server_name"] for agent in body["agents"])
    assert {tool["name"] for agent in body["agents"] for tool in agent["mcp_tools"]} == {
        "lookup_invoice",
        "review_code",
        "lookup_ticket",
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


def test_can_connect_and_browse_local_agent_workspace(client, tmp_path):
    workspace = tmp_path / "connected-agent"
    workspace.mkdir()
    (workspace / "agent.py").write_text("SYSTEM_PROMPT = 'help users'\n", encoding="utf-8")
    (workspace / ".env").write_text("OPENAI_API_KEY=hidden", encoding="utf-8")
    (workspace / "node_modules").mkdir()
    (workspace / "node_modules" / "ignored.js").write_text("ignored", encoding="utf-8")

    connected = client.post(
        "/api/workspaces/connect",
        json={
            "path": str(workspace),
            "name": "Connected Agent",
            "agent_id": "coding-agent",
        },
    )

    assert connected.status_code == 200
    body = connected.json()
    assert body["name"] == "Connected Agent"
    assert body["agent_id"] == "coding-agent"
    assert body["root_path"] == str(workspace.resolve())
    assert body["read_only"] is True
    workspace_id = body["id"]

    workspaces = client.get("/api/workspaces").json()["workspaces"]
    assert {item["id"] for item in workspaces} >= {"default", workspace_id}

    listing = client.get(f"/api/workspaces/{workspace_id}/files")
    assert listing.status_code == 200
    names = {entry["name"] for entry in listing.json()["entries"]}
    assert "agent.py" in names
    assert ".env" not in names
    assert "node_modules" not in names

    preview = client.get(
        f"/api/workspaces/{workspace_id}/file",
        params={"path": "agent.py"},
    )
    assert preview.status_code == 200
    assert "SYSTEM_PROMPT" in preview.json()["content"]

    traversal = client.get(
        f"/api/workspaces/{workspace_id}/file",
        params={"path": "../outside.txt"},
    )
    assert traversal.status_code == 403


def test_connect_workspace_rejects_unknown_agent_and_missing_path(client, tmp_path):
    missing = client.post(
        "/api/workspaces/connect",
        json={"path": str(tmp_path / "missing")},
    )
    assert missing.status_code == 404

    existing = tmp_path / "agent"
    existing.mkdir()
    unknown_agent = client.post(
        "/api/workspaces/connect",
        json={"path": str(existing), "agent_id": "unknown-agent"},
    )
    assert unknown_agent.status_code == 422


def test_agent_conversation_imports_context_runs_tool_and_verifies_output(client):
    response = client.post(
        "/api/conversations/message",
        json={
            "agent_id": "support-agent",
            "message": "What is the status of TCK-9001 and what should support do next?",
            "context_mode": "full",
        },
    )

    assert response.status_code == 200
    conversation = response.json()
    assert conversation["agent_id"] == "support-agent"
    answer = conversation["messages"][-1]
    assert "next step" in answer["content"].lower()
    assert answer["tool_calls"][0]["tool_name"] == "lookup_ticket"
    assert answer["verification"]["status"] == "verified"
    assert answer["verification"]["confidence"] > 0.9
    assert "Recent agent conversation history" in answer["context_used"]

    listed = client.get("/api/conversations", params={"agent_id": "support-agent"})
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == conversation["id"]


def test_managed_agent_configuration_can_be_edited_and_persisted(client):
    current = client.get("/api/managed-agents").json()[0]
    response = client.patch(
        f"/api/managed-agents/{current['id']}",
        json={
            "name": "Premium Finance Analyst",
            "description": "Explains invoice risk and payment status with current evidence.",
            "owner": "Premium Finance",
            "instructions": "Use current invoice data, state uncertainty clearly, and escalate unresolved billing exceptions.",
            "features": ["Invoice lookup", "Premium finance"],
            "response_style": "concise",
            "tool_policy": "approval",
            "enabled_tools": ["lookup_invoice"],
            "verification_mode": "strict",
            "memory_enabled": False,
        },
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["name"] == "Premium Finance Analyst"
    assert updated["tool_policy"] == "approval"
    assert updated["memory_enabled"] is False
    persisted = client.get("/api/managed-agents").json()[0]
    assert persisted["instructions"].startswith("Use current invoice data")


def test_manager_chat_selects_tools_stages_and_applies_agent_change(client):
    response = client.post(
        "/api/manager/message",
        json={
            "agent_id": "coding-agent",
            "message": "Make the agent explain whether a proposed code change is supported by test evidence.",
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
    assert all(": " in action["title"] for action in manager_message["actions"])
    assert {
        action["title"].split(":", 1)[0] for action in manager_message["actions"]
    } == {
        "Architecture Analyst",
        "Workspace Inspector",
        "Developer Specialist",
        "Validation Specialist",
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
        if item["id"] == "coding-agent"
    )
    assert "code change" in agent["instructions"]

    import backend.app.dependencies as dependencies

    instructions_file = (
        dependencies.store.path.parent
        / "managed_workspaces"
        / "coding-agent"
        / "instructions.md"
    )
    assert instructions_file.exists()
    assert "code change" in instructions_file.read_text(encoding="utf-8")


def test_manager_auto_mode_applies_validated_change_immediately(client):
    response = client.post(
        "/api/manager/message",
        json={
            "agent_id": "support-agent",
            "message": "Always explain next-step impact when a ticket is unresolved.",
            "autonomy": "auto",
        },
    )

    assert response.status_code == 200
    change = response.json()["messages"][-1]["changes"][0]
    assert change["status"] == "applied"
    agent = next(
        item
        for item in client.get("/api/managed-agents").json()
        if item["id"] == "support-agent"
    )
    assert "next-step impact" in agent["instructions"]


def test_build_prompt_is_validated(client):
    response = client.post("/api/builds", json={"prompt": "short"})
    assert response.status_code == 422
