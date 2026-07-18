from __future__ import annotations

import re
from typing import Any

from backend.app.infrastructure.mock_system import MockSystem


AGENT_ID = "finance-agent"
REQUIRED_TOOL = ("lookup-invoice", "lookup_invoice")


async def run(mock_system: MockSystem, message: str) -> dict[str, Any]:
    invoice_id = _identifier(message.upper(), r"INV-\d+", "INV-2048")
    output = await mock_system.get(f"/mock/invoices/{invoice_id}")
    content = (
        f"{invoice_id} is currently {output['status'].replace('_', ' ')}. "
        f"It totals {output['currency']} {output['amount']:.2f} and is due on {output['due_date']}. "
        f"Notes: {output['notes']}"
    )
    return {
        "tool_id": REQUIRED_TOOL[0],
        "tool_name": REQUIRED_TOOL[1],
        "inputs": {"invoice_id": invoice_id},
        "output": output,
        "content": content,
        "criteria": [
            "Identify the requested invoice",
            "Report its payment status and due date",
            "Ground the answer in the finance ledger",
        ],
        "evidence": [
            f"Invoice API returned status={output['status']}",
            f"Matched invoice_id={invoice_id}; source={output['_data_source']}",
        ],
    }


def _identifier(message: str, pattern: str, fallback: str) -> str:
    match = re.search(pattern, message)
    return match.group(0) if match else fallback
