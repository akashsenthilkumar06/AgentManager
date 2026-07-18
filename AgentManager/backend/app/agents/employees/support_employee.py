from __future__ import annotations

import re
from typing import Any

from backend.app.infrastructure.mock_system import MockSystem


AGENT_ID = "support-agent"
REQUIRED_TOOL = ("lookup-ticket", "lookup_ticket")


async def run(mock_system: MockSystem, message: str) -> dict[str, Any]:
    ticket_id = _identifier(message.upper(), r"TCK-\\d+", "TCK-9001")
    output = await mock_system.get(f"/mock/tickets/{ticket_id}")
    content = (
        f"{ticket_id} is {output['status'].replace('_', ' ')} with priority {output['priority']}. "
        f"Owner: {output['owner']}. Next step: {output['next_step']}"
    )
    return {
        "tool_id": REQUIRED_TOOL[0],
        "tool_name": REQUIRED_TOOL[1],
        "inputs": {"ticket_id": ticket_id},
        "output": output,
        "content": content,
        "criteria": [
            "Identify the requested support ticket",
            "Report the ticket owner and current status",
            "Explain the next support action",
        ],
        "evidence": [
            f"Ticket API returned status={output['status']}",
            f"Matched ticket_id={ticket_id}; source={output['_data_source']}",
        ],
    }


def _identifier(message: str, pattern: str, fallback: str) -> str:
    match = re.search(pattern, message)
    return match.group(0) if match else fallback
