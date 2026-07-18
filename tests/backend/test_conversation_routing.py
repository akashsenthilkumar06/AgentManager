from __future__ import annotations

import backend.app.dependencies as dependencies
from backend.app.core.models import (
    AgentRecord,
    MCPToolCapability,
    ToolRecord,
)


def _add_order_support_agent() -> None:
    input_schema = {
        "type": "object",
        "required": ["order_id"],
        "properties": {
            "order_id": {"type": "string"},
        },
    }
    dependencies.store.register_tool(
        ToolRecord(
            id="lookup-order",
            name="lookup_order",
            description="Looks up current order and fulfillment details.",
            owner="Order Support Agent",
            input_schema=input_schema,
            operation="lookup_order",
            probe_input={"order_id": "ORD-1042"},
        ).model_dump()
    )
    capability = MCPToolCapability(
        name="lookup_order",
        description="Looks up current order and fulfillment details.",
        input_schema=input_schema,
        tool_id="lookup-order",
        provider="manager_runtime",
    )
    architecture = dependencies.store.architecture()
    dependencies.store.update_agents(
        [
            *architecture.agents,
            AgentRecord(
                id="order-support-agent",
                name="Order Support Agent",
                description="Resolves order status questions.",
                owner="Customer Experience",
                tool_ids=["lookup-order"],
                mcp_endpoint="demo://order-support-agent",
                mcp_tools=[capability],
                enabled_tools=["lookup_order"],
                instructions=(
                    "Use current order data and never substitute unrelated "
                    "invoice or ticket records."
                ),
            ),
        ]
    )


def test_order_support_agent_executes_its_enabled_order_tool(client):
    _add_order_support_agent()

    response = client.post(
        "/api/conversations/message",
        json={
            "agent_id": "order-support-agent",
            "message": "What is the status of ORD-1042?",
        },
    )

    assert response.status_code == 200
    answer = response.json()["messages"][-1]
    assert answer["execution_mode"] == "deterministic"
    assert answer["tool_calls"][0]["tool_name"] == "lookup_order"
    assert answer["tool_calls"][0]["status"] == "passed"
    assert answer["tool_calls"][0]["input"] == {
        "order_id": "ORD-1042"
    }
    assert answer["tool_calls"][0]["output"]["status"] == "in_transit"
    assert answer["verification"]["status"] == "verified"


def test_order_agent_routes_invoice_identifier_without_fake_tool(client):
    _add_order_support_agent()

    response = client.post(
        "/api/conversations/message",
        json={
            "agent_id": "order-support-agent",
            "message": "What company is associated with INV-1045?",
        },
    )

    assert response.status_code == 200
    answer = response.json()["messages"][-1]
    assert answer["tool_calls"][0]["tool_name"] == (
        "capability_mismatch"
    )
    assert answer["tool_calls"][0]["status"] == "failed"
    assert answer["tool_calls"][0]["output"]["requested_field"] == (
        "invoice_id"
    )
    assert answer["tool_calls"][0]["output"]["suggested_agent"] == (
        "Finance Analyst"
    )
    assert "cannot handle this invoice id request" in answer[
        "content"
    ]
    assert "unavailable is disabled" not in answer["content"]
