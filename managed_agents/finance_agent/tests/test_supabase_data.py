from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from managed_agents.finance_agent.supabase_data import query_invoices


class _Response:
    def __init__(self, rows: list[dict], content_range: str):
        self._body = json.dumps(rows).encode("utf-8")
        self.headers = {"Content-Range": content_range}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self) -> bytes:
        return self._body


class SupabaseInvoiceQueryTests(unittest.TestCase):
    def test_query_is_filtered_bounded_and_returns_live_evidence(self):
        rows = [
            {
                "invoice_id": "INV-9001",
                "customer_name": "Example",
                "status": "past_due",
                "amount": 125.25,
                "due_date": "2026-07-01",
                "notes": "Test fixture",
                "updated_at": "2026-07-18T00:00:00Z",
            },
            {
                "invoice_id": "INV-9002",
                "customer_name": "Example",
                "status": "past_due",
                "amount": 74.75,
                "due_date": "2026-07-02",
                "notes": "Test fixture",
                "updated_at": "2026-07-18T00:00:00Z",
            },
        ]
        with patch.dict(
            os.environ,
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_SECRET_KEY": "secret-test-value",
                "SUPABASE_FINANCE_TABLE": "finance_invoices",
            },
            clear=False,
        ), patch(
            "managed_agents.finance_agent.supabase_data.urlopen",
            return_value=_Response(rows, "0-1/2"),
        ) as request:
            result = query_invoices(status="past_due", limit=10)

        url = request.call_args.args[0].full_url
        self.assertIn("/rest/v1/finance_invoices?", url)
        self.assertIn("status=eq.past_due", url)
        self.assertIn("limit=10", url)
        self.assertEqual(result["returned_count"], 2)
        self.assertEqual(result["total_matching"], 2)
        self.assertEqual(result["total_amount"], 200.0)
        self.assertEqual(
            result["source"],
            "supabase://database/finance_invoices",
        )
        self.assertTrue(result["evidence"]["pulled_live"])
        self.assertNotIn("secret-test-value", json.dumps(result))

    def test_rejects_unbounded_or_unsafe_filters(self):
        with self.assertRaisesRegex(ValueError, "between 1 and 100"):
            query_invoices(limit=101)
        with self.assertRaisesRegex(
            ValueError,
            "unsupported characters",
        ):
            query_invoices(status="past_due&select=*")


if __name__ == "__main__":
    unittest.main()
