"""Standalone MCP agent and live-conversation integration tests."""

from __future__ import annotations

import json

import httpx

import backend.app.dependencies as dependencies
from external_agent.app import app as external_agent_app


def _agent_update(agent: dict, endpoint: str) -> dict:
    return {
        "name": agent["name"],
        "description": agent["description"],
        "owner": agent["owner"],
        "mcp_endpoint": endpoint,
        "instructions": agent["instructions"],
        "features": agent["features"],
        "response_style": agent["response_style"],
        "tool_policy": agent["tool_policy"],
        "enabled_tools": agent["enabled_tools"],
        "verification_mode": agent["verification_mode"],
        "memory_enabled": agent["memory_enabled"],
    }


def test_endpoint_update_discovers_and_calls_standalone_mcp_agent(
    client,
    monkeypatch,
):
    transport = httpx.ASGITransport(app=external_agent_app)
    monkeypatch.setattr(dependencies.mcp_client, "transport", transport)
    monkeypatch.setattr(
        dependencies.live_conversation_runner,
        "api_key",
        "test-openai-key",
    )

    responses: list[dict] = []

    async def fake_openai_response(_client, body):
        responses.append(body)
        if len(responses) == 1:
            advertised_names = {tool["name"] for tool in body["tools"]}
            assert "support_lookup_ticket" in advertised_names
            return {
                "output": [
                    {
                        "type": "reasoning",
                        "id": "reasoning_live_1",
                        "summary": [],
                    },
                    {
                        "type": "function_call",
                        "id": "function_live_1",
                        "call_id": "call_live_1",
                        "name": "support_lookup_ticket",
                        "arguments": json.dumps({"ticket_id": "TCK-9001"}),
                    },
                ]
            }

        tool_outputs = [
            item
            for item in body["input"]
            if item.get("type") == "function_call_output"
        ]
        assert len(tool_outputs) == 1
        live_result = json.loads(tool_outputs[0]["output"])
        assert live_result["source"] == "standalone-external-agent"
        assert live_result["proof"] == "LIVE-MCP-TCK-9001"
        return {
            "output": [
                {
                    "type": "message",
                    "id": "message_live_1",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": (
                                "TCK-9001 is investigating. "
                                "Source: standalone-external-agent. "
                                "Proof: LIVE-MCP-TCK-9001."
                            ),
                        }
                    ],
                }
            ],
            "output_text": (
                "TCK-9001 is investigating. "
                "Source: standalone-external-agent. "
                "Proof: LIVE-MCP-TCK-9001."
            ),
        }

    monkeypatch.setattr(
        dependencies.live_conversation_runner,
        "_create_response",
        fake_openai_response,
    )

    agent = client.get("/api/managed-agents").json()[0]
    endpoint = "http://standalone-agent.test/mcp"
    updated = client.patch(
        f"/api/managed-agents/{agent['id']}",
        json=_agent_update(agent, endpoint),
    )
    assert updated.status_code == 200
    assert updated.json()["mcp_endpoint"] == endpoint
    assert updated.json()["mcp_tools"] == []
    assert updated.json()["status"] == "degraded"

    discovered = client.post(
        f"/api/managed-agents/{agent['id']}/discover",
        json={},
    )
    assert discovered.status_code == 200
    discovered_agent = discovered.json()
    assert discovered_agent["mcp_server_name"] == "standalone-support-agent"
    assert {
        tool["name"] for tool in discovered_agent["mcp_tools"]
    } == {
        "support.lookup_ticket",
        "support.estimate_resolution",
    }
    assert set(discovered_agent["enabled_tools"]) == {
        "support.lookup_ticket",
        "support.estimate_resolution",
    }

    conversation = client.post(
        "/api/conversations/message",
        json={
            "agent_id": agent["id"],
            "message": "Look up TCK-9001 and include the live proof.",
            "context_mode": "full",
        },
    )
    assert conversation.status_code == 200
    answer = conversation.json()["messages"][-1]
    assert answer["execution_mode"] == "live"
    assert answer["provider"] == "openai:gpt-5-mini+mcp"
    assert answer["endpoint"] == endpoint
    assert answer["fallback_reason"] is None
    assert answer["tool_calls"][0]["tool_name"] == "support.lookup_ticket"
    assert answer["tool_calls"][0]["output"]["source"] == (
        "standalone-external-agent"
    )
    assert answer["tool_calls"][0]["output"]["proof"] == "LIVE-MCP-TCK-9001"
    assert "LIVE-MCP-TCK-9001" in answer["content"]
    assert answer["verification"]["status"] == "verified"
    assert len(responses) == 2


def test_http_agent_without_llm_key_uses_visible_fallback(client, monkeypatch):
    monkeypatch.setattr(
        dependencies.live_conversation_runner,
        "api_key",
        None,
    )
    agent = client.get("/api/managed-agents").json()[0]
    endpoint = "http://127.0.0.1:8100/mcp"
    updated = client.patch(
        f"/api/managed-agents/{agent['id']}",
        json=_agent_update(agent, endpoint),
    )
    assert updated.status_code == 200

    conversation = client.post(
        "/api/conversations/message",
        json={
            "agent_id": agent["id"],
            "message": "What is the status of ORD-1042?",
            "context_mode": "minimal",
        },
    )
    assert conversation.status_code == 200
    answer = conversation.json()["messages"][-1]
    assert answer["execution_mode"] == "fallback"
    assert answer["provider"] == "local:fallback"
    assert answer["endpoint"] == endpoint
    assert answer["fallback_reason"] == "OPENAI_API_KEY is not configured"
    assert answer["tool_calls"][0]["tool_name"] == "lookup_order"
    assert answer["verification"]["evidence"][0].startswith(
        "Live MCP unavailable; deterministic fallback:"
    )


def test_endpoint_validation_rejects_unsupported_schemes(client):
    agent = client.get("/api/managed-agents").json()[0]
    response = client.patch(
        f"/api/managed-agents/{agent['id']}",
        json=_agent_update(agent, "file:///tmp/not-an-mcp-server"),
    )
    assert response.status_code == 422


def test_discovery_connection_failure_returns_actionable_error(
    client,
    monkeypatch,
):
    def fail_connection(request):
        raise httpx.ConnectError("test agent refused the connection", request=request)

    monkeypatch.setattr(
        dependencies.mcp_client,
        "transport",
        httpx.MockTransport(fail_connection),
    )
    agent = client.get("/api/managed-agents").json()[0]
    endpoint = "http://offline-agent.test/mcp"
    updated = client.patch(
        f"/api/managed-agents/{agent['id']}",
        json=_agent_update(agent, endpoint),
    )
    assert updated.status_code == 200

    response = client.post(
        f"/api/managed-agents/{agent['id']}/discover",
        json={},
    )
    assert response.status_code == 502
    assert response.json()["detail"].startswith(
        "Could not connect to the MCP endpoint:"
    )
