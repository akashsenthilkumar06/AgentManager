from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

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

CUSTOMERS = {
    "CUS-88": {
        "customer_id": "CUS-88",
        "tier": "Gold",
        "preferred_channel": "email",
        "locale": "en-US",
    },
    "CUS-23": {
        "customer_id": "CUS-23",
        "tier": "Standard",
        "preferred_channel": "sms",
        "locale": "en-US",
    },
}


def match(path: str) -> dict[str, Any] | None:
    ticket = re.match(r"^/mock/tickets/([^/]+)$", path)
    if ticket:
        ticket_id = ticket.group(1).upper()
        if ticket_id not in TICKETS:
            raise LookupError(f"No record found for {ticket_id}")
        return deepcopy(TICKETS[ticket_id])

    customer = re.match(r"^/mock/customers/([^/]+)$", path)
    if customer:
        customer_id = customer.group(1).upper()
        if customer_id not in CUSTOMERS:
            raise LookupError(f"No record found for {customer_id}")
        return deepcopy(CUSTOMERS[customer_id])

    return None
