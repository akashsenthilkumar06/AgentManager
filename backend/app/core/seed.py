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
            id="orders-api",
            name="Order details API",
            path="/mock/orders/{order_id}",
            description="Returns the lifecycle, customer, value, and fulfillment state for an order.",
            owner="Commerce Platform",
            tags=["orders", "commerce", "status"],
            latency_ms=42,
        ),
        EndpointRecord(
            id="shipments-api",
            name="Shipment events API",
            path="/mock/shipments/by-order/{order_id}",
            description="Returns carrier events, ETA, exceptions, and delay information for an order.",
            owner="Logistics",
            tags=["shipping", "logistics", "tracking", "delay"],
            latency_ms=67,
        ),
        EndpointRecord(
            id="inventory-api",
            name="Inventory availability API",
            path="/mock/inventory/{sku}",
            description="Returns on-hand, reserved, and available quantities by SKU.",
            owner="Supply Chain",
            tags=["inventory", "stock", "sku"],
            latency_ms=31,
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
            id="lookup-order",
            name="lookup_order",
            description="Looks up core order details for support workflows.",
            owner="Order Support Agent",
            endpoint_ids=["orders-api"],
            input_schema={"type": "object", "required": ["order_id"], "properties": {"order_id": {"type": "string"}}},
            output_schema={"type": "object", "properties": {"status": {"type": "string"}}},
            operation="lookup_order",
            probe_input={"order_id": "ORD-1042"},
        ),
        ToolRecord(
            id="track-shipment",
            name="track_shipment",
            description="Retrieves the latest shipment event and expected delivery date.",
            owner="Logistics Agent",
            endpoint_ids=["shipments-api"],
            input_schema={"type": "object", "required": ["order_id"], "properties": {"order_id": {"type": "string"}}},
            output_schema={"type": "object", "properties": {"eta": {"type": "string"}}},
            operation="track_shipment",
            probe_input={"order_id": "ORD-1042"},
        ),
        ToolRecord(
            id="check-inventory",
            name="check_inventory",
            description="Checks available-to-promise inventory for a SKU.",
            owner="Catalog Agent",
            endpoint_ids=["inventory-api"],
            input_schema={"type": "object", "required": ["sku"], "properties": {"sku": {"type": "string"}}},
            output_schema={"type": "object", "properties": {"available": {"type": "integer"}}},
            operation="check_inventory",
            probe_input={"sku": "SKU-RED-42"},
        ),
    ]
    agents = [
        AgentRecord(
            id="order-support-agent",
            name="Order Support Agent",
            description="Resolves common order questions and escalates fulfillment exceptions.",
            owner="Customer Experience",
            tool_ids=["lookup-order"],
            mcp_endpoint="demo://order-support-agent",
            features=["Order lookup", "Support triage"],
            instructions="Resolve order questions using current system data. Be clear about status, avoid assumptions, and recommend escalation when fulfillment evidence is incomplete.",
            enabled_tools=["lookup_order"],
        ),
        AgentRecord(
            id="logistics-agent",
            name="Logistics Agent",
            description="Tracks shipment movement and identifies carrier exceptions.",
            owner="Logistics",
            tool_ids=["track-shipment"],
            mcp_endpoint="demo://logistics-agent",
            features=["Shipment tracking", "Carrier exception detection"],
            instructions="Track shipment movement using carrier events. Always surface the latest event, delivery estimate, and any active exception or delay.",
            enabled_tools=["track_shipment"],
            verification_mode="strict",
        ),
        AgentRecord(
            id="catalog-agent",
            name="Catalog Agent",
            description="Answers product availability questions using live inventory.",
            owner="Merchandising",
            tool_ids=["check-inventory"],
            mcp_endpoint="demo://catalog-agent",
            features=["Inventory availability", "Stockout risk"],
            instructions="Answer availability questions from live inventory quantities. Explain available, on-hand, and reserved stock without promising future replenishment.",
            enabled_tools=["check_inventory"],
        ),
    ]
    sources = [
        DataSourceRecord(id="commerce-db", name="Commerce read replica", kind="PostgreSQL", description="Order and fulfillment metadata.", owner="Commerce Platform"),
        DataSourceRecord(id="carrier-stream", name="Carrier event stream", kind="Kafka", description="Normalized carrier scans and delivery events.", owner="Logistics"),
        DataSourceRecord(id="inventory-cache", name="Inventory cache", kind="Redis", description="Near-real-time available-to-promise counts.", owner="Supply Chain"),
    ]
    return ArchitectureState(agents=agents, tools=tools, endpoints=endpoints, data_sources=sources)
