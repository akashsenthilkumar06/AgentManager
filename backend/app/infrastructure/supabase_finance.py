"""Server-only reader for the finance demo's Supabase table."""

from __future__ import annotations

from typing import Any

import httpx


DEMO_INVOICES = [
    {"invoice_id": "INV-2048", "customer_name": "Acme Labs", "amount": 1840.50, "status": "past_due", "due_date": "2026-07-15"},
    {"invoice_id": "INV-3019", "customer_name": "Northstar Co.", "amount": 2250.00, "status": "past_due", "due_date": "2026-07-10"},
    {"invoice_id": "INV-1120", "customer_name": "Bluebird Inc.", "amount": 420.00, "status": "paid", "due_date": "2026-07-06"},
]


class SupabaseFinanceRepository:
    """Returns normalized invoice rows without ever returning credentials."""

    def __init__(self, url: str | None, secret_key: str | None, table: str) -> None:
        self.url = url.rstrip("/") if url else None
        self.secret_key = secret_key
        self.table = table

    async def invoices(self) -> tuple[list[dict[str, Any]], str]:
        if not self.url:
            return [dict(row) for row in DEMO_INVOICES], "local-demo-data"
        if not self.secret_key:
            raise PermissionError(
                "SUPABASE_SECRET_KEY is required when SUPABASE_URL is configured"
            )
        headers = {
            "apikey": self.secret_key,
            "Authorization": f"Bearer {self.secret_key}",
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{self.url}/rest/v1/{self.table}",
                params={"select": "*"},
                headers=headers,
            )
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("Supabase finance table must return a JSON list")
        rows = [self._normalize(row) for row in payload if isinstance(row, dict)]
        if not rows:
            raise LookupError(f"No invoice rows found in Supabase table '{self.table}'")
        return rows, "supabase"

    @staticmethod
    def _normalize(row: dict[str, Any]) -> dict[str, Any]:
        required = ("invoice_id", "amount", "status", "due_date")
        missing = [field for field in required if row.get(field) in (None, "")]
        if missing:
            raise ValueError("Finance table is missing values for: " + ", ".join(missing))
        return {
            "invoice_id": str(row["invoice_id"]),
            "customer_name": str(row.get("customer_name") or "Unassigned customer"),
            "amount": float(row["amount"]),
            "status": str(row["status"]).lower(),
            "due_date": str(row["due_date"]),
        }
