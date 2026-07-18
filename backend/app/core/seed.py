from __future__ import annotations

from backend.app.core.models import (
    AgentRecord,
    ArchitectureState,
    DataSourceRecord,
    EndpointRecord,
    ToolRecord,
)


def demo_architecture() -> ArchitectureState:
    endpoints = [
        EndpointRecord(
            id="invoices-api",
            name="Invoice ledger API",
            path="/mock/invoices/{invoice_id}",
            description="Returns invoice status, due date, amount, and payment notes.",
            owner="Finance",
            tags=["finance", "billing", "invoice"],
            latency_ms=39,
        ),
        EndpointRecord(
            id="codebase-api",
            name="Codebase health API",
            path="/mock/codebase/{repo_id}",
            description="Returns repository health, coverage, and active issue signals.",
            owner="Engineering",
            tags=["code", "testing", "review"],
            latency_ms=44,
        ),
        EndpointRecord(
            id="tickets-api",
            name="Support ticket API",
            path="/mock/tickets/{ticket_id}",
            description="Returns ticket state, priority, customer context, and next action.",
            owner="Support",
            tags=["support", "ticket", "customer"],
            latency_ms=36,
        ),
        EndpointRecord(
            id="customers-api",
            name="Customer profile API",
            path="/mock/customers/{customer_id}",
            description="Returns customer tier and non-sensitive support preferences.",
            owner="Customer Experience",
            tags=["customer", "profile", "support"],
            latency_ms=38,
        ),
    ]
    tools = [
        ToolRecord(
            id="lookup-invoice",
            name="lookup_invoice",
            description="Looks up invoice status and payment details for finance workflows.",
            owner="Finance Analyst",
            endpoint_ids=["invoices-api"],
            input_schema={"type": "object", "required": ["invoice_id"], "properties": {"invoice_id": {"type": "string"}}},
            output_schema={"type": "object", "properties": {"status": {"type": "string"}}},
            operation="lookup_invoice",
            probe_input={"invoice_id": "INV-2048"},
        ),
        ToolRecord(
            id="review-code",
            name="review_code",
            description="Checks repository health and highlights release risk for engineering workflows.",
            owner="Coding Agent",
            endpoint_ids=["codebase-api"],
            input_schema={"type": "object", "required": ["repo_id"], "properties": {"repo_id": {"type": "string"}}},
            output_schema={"type": "object", "properties": {"coverage": {"type": "number"}}},
            operation="review_code",
            probe_input={"repo_id": "REPO-1"},
        ),
        ToolRecord(
            id="lookup-ticket",
            name="lookup_ticket",
            description="Retrieves ticket state, context, and next-step guidance for support workflows.",
            owner="Support Agent",
            endpoint_ids=["tickets-api", "customers-api"],
            input_schema={"type": "object", "required": ["ticket_id"], "properties": {"ticket_id": {"type": "string"}}},
            output_schema={"type": "object", "properties": {"status": {"type": "string"}}},
            operation="lookup_ticket",
            probe_input={"ticket_id": "TCK-9001"},
        ),
    ]
    agents = [
        AgentRecord(
            id="finance-agent",
            name="Finance Analyst",
            description="Explains invoice status, payment risk, and billing exceptions.",
            owner="Finance",
            tool_ids=["lookup-invoice"],
            mcp_endpoint="demo://finance-agent",
            features=["Invoice lookup", "Billing risk analysis"],
            instructions="Explain invoice status using current ledger data. Call out unpaid balances, due dates, and payment risk with no guesswork.",
            enabled_tools=["lookup_invoice"],
        ),
        AgentRecord(
            id="coding-agent",
            name="Coding Agent",
            description="Reviews repository health and flags release risk before deployment.",
            owner="Engineering",
            tool_ids=["review-code"],
            mcp_endpoint="demo://coding-agent",
            features=["Code review", "Test health", "Release risk"],
            instructions="Review codebase health using current repo signals. Surface coverage, failing tests, and release risk before making recommendations.",
            enabled_tools=["review_code"],
            verification_mode="strict",
        ),
        AgentRecord(
            id="support-agent",
            name="Support Agent",
            description="Handles ticket status, customer context, and next-step support actions.",
            owner="Support",
            tool_ids=["lookup-ticket"],
            mcp_endpoint="demo://support-agent",
            features=["Ticket lookup", "Customer context", "Support triage"],
            instructions="Answer support questions from live ticket state. Make the next action explicit and escalate only when the ticket data supports it.",
            enabled_tools=["lookup_ticket"],
        ),
    ]
    sources = [
        DataSourceRecord(id="commerce-db", name="Commerce read replica", kind="PostgreSQL", description="Order and fulfillment metadata.", owner="Commerce Platform"),
        DataSourceRecord(id="carrier-stream", name="Carrier event stream", kind="Kafka", description="Normalized carrier scans and delivery events.", owner="Logistics"),
        DataSourceRecord(id="inventory-cache", name="Inventory cache", kind="Redis", description="Near-real-time available-to-promise counts.", owner="Supply Chain"),
    ]
    return ArchitectureState(agents=agents, tools=tools, endpoints=endpoints, data_sources=sources)
