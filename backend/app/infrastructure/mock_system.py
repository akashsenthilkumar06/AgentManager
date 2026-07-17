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

SHIPMENTS = {
    "ORD-1042": {
        "order_id": "ORD-1042",
        "tracking_number": "1Z83A04",
        "carrier": "UPS",
        "status": "in_transit",
        "latest_event": "Departed regional facility",
        "eta": "2026-07-18",
        "exception": "Weather delay near Memphis hub",
        "delay_hours": 14,
    },
    "ORD-2048": {
        "order_id": "ORD-2048",
        "tracking_number": "9405511",
        "carrier": "USPS",
        "status": "delivered",
        "latest_event": "Delivered at front door",
        "eta": "2026-07-11",
        "exception": None,
        "delay_hours": 0,
    },
}

INVENTORY = {
    "SKU-RED-42": {"sku": "SKU-RED-42", "on_hand": 148, "reserved": 29, "available": 119, "location_count": 4},
    "SKU-BLU-07": {"sku": "SKU-BLU-07", "on_hand": 8, "reserved": 8, "available": 0, "location_count": 1},
}

CUSTOMERS = {
    "CUS-88": {"customer_id": "CUS-88", "tier": "Gold", "preferred_channel": "email", "locale": "en-US"},
    "CUS-23": {"customer_id": "CUS-23", "tier": "Standard", "preferred_channel": "sms", "locale": "en-US"},
}


class MockSystem:
    """In-process stand-in for the existing enterprise APIs in the demo."""

    async def get(self, path: str) -> dict[str, Any]:
        await asyncio.sleep(0.006)
        patterns = [
            (r"^/mock/orders/([^/]+)$", ORDERS),
            (r"^/mock/shipments/by-order/([^/]+)$", SHIPMENTS),
            (r"^/mock/inventory/([^/]+)$", INVENTORY),
            (r"^/mock/customers/([^/]+)$", CUSTOMERS),
        ]
        for pattern, records in patterns:
            match = re.match(pattern, path)
            if match:
                key = match.group(1).upper()
                if key not in records:
                    raise LookupError(f"No record found for {key}")
                return deepcopy(records[key])
        raise LookupError(f"Unknown endpoint: {path}")
