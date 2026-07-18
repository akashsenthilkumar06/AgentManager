"""Deterministic stand-ins for enterprise systems used by the demo."""

from __future__ import annotations

import asyncio
import re
from copy import deepcopy
from typing import Any


ORDERS = {
    "ORD-1042": {
        "order_id": "ORD-1042",
        "status": "in_transit",
        "customer_id": "CUS-88",
        "placed_at": "2026-07-12T14:24:00Z",
        "total": 128.40,
        "currency": "USD",
        "items": 3,
    },
    "ORD-2048": {
        "order_id": "ORD-2048",
        "status": "delivered",
        "customer_id": "CUS-23",
        "placed_at": "2026-07-08T09:05:00Z",
        "total": 64.99,
        "currency": "USD",
        "items": 1,
    },
}

CUSTOMERS = {
    "CUS-88": {"customer_id": "CUS-88", "tier": "Gold", "preferred_channel": "email", "locale": "en-US"},
    "CUS-23": {"customer_id": "CUS-23", "tier": "Standard", "preferred_channel": "sms", "locale": "en-US"},
}

INVOICES = {
    "INV-2048": {
        "invoice_id": "INV-2048",
        "customer_id": "CUS-88",
        "status": "past_due",
        "amount": 1840.50,
        "currency": "USD",
        "due_date": "2026-07-15",
        "notes": "Partial payment received; finance follow-up needed.",
    },
    "INV-1120": {
        "invoice_id": "INV-1120",
        "customer_id": "CUS-23",
        "status": "paid",
        "amount": 420.00,
        "currency": "USD",
        "due_date": "2026-07-06",
        "notes": "Closed out in full.",
    },
}

CODEBASE = {
    "REPO-1": {
        "repo_id": "REPO-1",
        "branch": "main",
        "status": "needs_review",
        "coverage": 86.4,
        "failing_tests": 2,
        "open_issues": 5,
        "risk": "medium",
        "summary": "Recent changes touched shared utilities and test coverage slipped below the release threshold.",
    }
}

TICKETS = {
    "TCK-9001": {
        "ticket_id": "TCK-9001",
        "customer_id": "CUS-88",
        "status": "investigating",
        "priority": "high",
        "owner": "Tier 2 Support",
        "next_step": "Collect account details and confirm billing history.",
    },
    "TCK-9012": {
        "ticket_id": "TCK-9012",
        "customer_id": "CUS-23",
        "status": "resolved",
        "priority": "low",
        "owner": "Tier 1 Support",
        "next_step": "Send closure summary to customer.",
    },
}


class MockSystem:
    """In-process stand-in for the existing enterprise APIs in the demo."""

    async def execute_operation(
        self,
        operation: str | None,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if operation == "lookup_order":
            key = str(payload.get("order_id", "")).upper()
            return await self.get("/mock/orders/" + key)
        if operation == "track_shipment":
            key = str(payload.get("order_id", "")).upper()
            return await self.get("/mock/shipments/by-order/" + key)
        if operation == "check_inventory":
            key = str(payload.get("sku", "")).upper()
            return await self.get("/mock/inventory/" + key)
        raise ValueError("Tool has no executable operation")

    async def get(self, path: str) -> dict[str, Any]:
        await asyncio.sleep(0.006)
        patterns = [
            (r"^/mock/orders/([^/]+)$", ORDERS),
            (r"^/mock/customers/([^/]+)$", CUSTOMERS),
            (r"^/mock/invoices/([^/]+)$", INVOICES),
            (r"^/mock/codebase/([^/]+)$", CODEBASE),
            (r"^/mock/tickets/([^/]+)$", TICKETS),
        ]
        for pattern, records in patterns:
            match = re.match(pattern, path)
            if match:
                key = match.group(1).upper()
                if key not in records:
                    raise LookupError(f"No record found for {key}")
                return deepcopy(records[key])
        raise LookupError(f"Unknown endpoint: {path}")
