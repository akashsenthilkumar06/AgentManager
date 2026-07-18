from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

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


def match(path: str) -> dict[str, Any] | None:
    matched = re.match(r"^/mock/invoices/([^/]+)$", path)
    if not matched:
        return None
    invoice_id = matched.group(1).upper()
    if invoice_id not in INVOICES:
        raise LookupError(f"No record found for {invoice_id}")
    return deepcopy(INVOICES[invoice_id])
