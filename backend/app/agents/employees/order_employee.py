from __future__ import annotations

import re
from typing import Any

from backend.app.infrastructure.mock_system import MockSystem


AGENT_ID = "order-support-agent"
REQUIRED_TOOL = ("lookup-order", "lookup_order")


async def run(mock_system: MockSystem, message: str) -> dict[str, Any]:
    order_id = _identifier(message.upper(), r"ORD-\d+", "ORD-1042")
    output = await mock_system.get(f"/mock/orders/{order_id}")
    content = (
        f"{order_id} is currently "
        f"{output['status'].replace('_', ' ')}. "
        f"It contains {output['items']} items totaling "
        f"{output['currency']} {output['total']:.2f} and was placed on "
        f"{output['placed_at']}."
    )
    return {
        "tool_id": REQUIRED_TOOL[0],
        "tool_name": REQUIRED_TOOL[1],
        "inputs": {"order_id": order_id},
        "output": output,
        "content": content,
        "criteria": [
            "Identify the requested order",
            "Report the current fulfillment status",
            "Ground the answer in the order lookup result",
        ],
        "evidence": [
            f"Order API returned status={output['status']}",
            f"Matched order_id={order_id}; "
            f"source={output['_data_source']}",
        ],
    }


def _identifier(message: str, pattern: str, fallback: str) -> str:
    match = re.search(pattern, message)
    return match.group(0) if match else fallback
