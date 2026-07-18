"""Standing fleet reconciliation and autonomous finding tests."""

from __future__ import annotations

import asyncio

import httpx

import backend.app.dependencies as dependencies
from backend.app.core.models import MCPToolCapability
from external_agent.app import app as external_agent_app


def test_reconciliation_baseline_is_visible_without_findings(client):
    overview = client.get("/api/overview").json()

    assert overview["reconciliation"]["mode"] == "edge_triggered"
    assert overview["reconciliation"]["last_checked_at"]
    assert overview["reconciliation"]["summary"]["agents_scanned"] == 3
    assert overview["reconciliation"]["summary"]["token_usage"] == 0
    assert overview["standing_findings"] == []
    assert client.get("/api/findings").json() == []


def test_reconciliation_detects_drift_duplicates_and_contract_conflicts(
    client,
):
    architecture = dependencies.store.architecture()
    order_tool = next(
        tool for tool in architecture.tools if tool.id == "lookup-order"
    )
    shipment_tool = next(
        tool for tool in architecture.tools if tool.id == "track-shipment"
    )
    logistics = next(
        agent
        for agent in architecture.agents
        if agent.id == "logistics-agent"
    )
    catalog = next(
        agent
        for agent in architecture.agents
        if agent.id == "catalog-agent"
    )
    duplicate = MCPToolCapability(
        name=order_tool.name,
        description=order_tool.description,
        input_schema=order_tool.input_schema,
        provider="agent_mcp",
        provider_endpoint="https://independent-orders.test/mcp",
    )
    conflict = MCPToolCapability(
        name=shipment_tool.name,
        description="An incompatible independently configured shipment tool.",
        input_schema={
            "type": "object",
            "required": ["tracking_number"],
            "properties": {
                "tracking_number": {"type": "string"},
            },
        },
        provider="agent_mcp",
        provider_endpoint="https://independent-shipping.test/mcp",
    )
    dependencies.store.update_agent(
        logistics.model_copy(
            update={"attached_tools": [duplicate]}
        )
    )
    dependencies.store.update_agent(
        catalog.model_copy(
            update={"attached_tools": [conflict]}
        )
    )

    run = asyncio.run(dependencies.monitoring_agent.reconcile_once())
    findings = dependencies.store.findings()
    kinds = {finding.kind for finding in findings}

    assert run["summary"]["token_usage"] == 0
    assert {
        "capability_drift",
        "duplicate_capability",
        "capability_conflict",
    }.issubset(kinds)
    duplicate_finding = next(
        finding
        for finding in findings
        if finding.kind == "duplicate_capability"
    )
    assert duplicate_finding.origin == "standing_reconciliation"
    assert duplicate_finding.status == "open"
    assert duplicate_finding.trigger is not None
    assert duplicate_finding.trigger.agent == "ArchitectureAgent"
    assert duplicate_finding.trigger.status == "completed"
    assert "without an OpenAI call" in duplicate_finding.trigger.detail
    assert {"logistics-agent", "order-support-agent"}.issubset(
        duplicate_finding.agent_ids
    )

    first_ids = {
        finding.key: finding.id
        for finding in dependencies.store.findings()
    }
    asyncio.run(dependencies.monitoring_agent.reconcile_once())
    second = dependencies.store.findings()
    assert {
        finding.key: finding.id for finding in second
    }.items() >= first_ids.items()
    assert len(
        [
            finding
            for finding in second
            if finding.kind == "duplicate_capability"
        ]
    ) == 1
    assert len(
        [
            finding
            for finding in second
            if finding.kind == "capability_conflict"
        ]
    ) == 1

    open_findings = client.get(
        "/api/findings",
        params={"status": "open"},
    ).json()
    assert {
        finding["kind"] for finding in open_findings
    } >= {"duplicate_capability", "capability_conflict"}
    observed = client.get(
        "/api/findings",
        params={"status": "observed"},
    ).json()
    assert any(
        finding["kind"] == "capability_drift"
        for finding in observed
    )


def test_reconciliation_records_endpoint_failure_and_resolution(
    client,
    monkeypatch,
):
    architecture = dependencies.store.architecture()
    agent = next(
        item
        for item in architecture.agents
        if item.id == "order-support-agent"
    )
    endpoint = "http://standing-agent.test/mcp"
    dependencies.store.update_agent(
        agent.model_copy(
            update={
                "mcp_endpoint": endpoint,
                "mcp_tools": [],
                "enabled_tools": [],
                "status": "degraded",
            }
        )
    )

    def fail_connection(request):
        raise httpx.ConnectError(
            "standing check refused",
            request=request,
        )

    monkeypatch.setattr(
        dependencies.mcp_client,
        "transport",
        httpx.MockTransport(fail_connection),
    )
    asyncio.run(dependencies.monitoring_agent.reconcile_once())

    failed = dependencies.store.get_finding(
        "endpoint:order-support-agent"
    )
    assert failed is not None
    assert failed.status == "open"
    assert failed.severity == "critical"
    assert "standing check refused" in failed.detail
    degraded = next(
        item
        for item in dependencies.store.architecture().agents
        if item.id == "order-support-agent"
    )
    assert degraded.status == "degraded"

    monkeypatch.setattr(
        dependencies.mcp_client,
        "transport",
        httpx.ASGITransport(app=external_agent_app),
    )
    asyncio.run(dependencies.monitoring_agent.reconcile_once())

    resolved = dependencies.store.get_finding(
        "endpoint:order-support-agent"
    )
    assert resolved is not None
    assert resolved.status == "resolved"
    assert resolved.resolved_at is not None
    refreshed = next(
        item
        for item in dependencies.store.architecture().agents
        if item.id == "order-support-agent"
    )
    assert refreshed.status == "healthy"
    assert {
        tool.name for tool in refreshed.mcp_tools
    } == {
        "support.lookup_ticket",
        "support.estimate_resolution",
    }
    resolved_api = client.get(
        "/api/findings",
        params={"status": "resolved"},
    ).json()
    assert any(
        finding["key"] == "endpoint:order-support-agent"
        for finding in resolved_api
    )
