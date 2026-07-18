"""Deterministic finance-agent failure and manager-correction demonstration."""

from __future__ import annotations

from typing import Any

from backend.app.infrastructure.supabase_finance import SupabaseFinanceRepository


class FinanceDemoAgent:
    def __init__(self, finance_repository: SupabaseFinanceRepository) -> None:
        self.finance_repository = finance_repository

    async def run(self, inject_failure: bool = True) -> dict[str, Any]:
        invoices, source = await self.finance_repository.invoices()
        overdue = [row for row in invoices if row["status"] == "past_due"]
        if not overdue:
            raise LookupError("The finance table has no past_due invoices for the demo")
        expected = self._analysis(overdue)
        employee_rows = (
            [max(overdue, key=lambda row: row["due_date"])]
            if inject_failure and len(overdue) > 1
            else overdue
        )
        employee = self._analysis(employee_rows)
        employee["mode"] = "intentional-demo-failure" if employee_rows != overdue else "complete-analysis"
        missed = [row for row in overdue if row["invoice_id"] not in employee["invoice_ids"]]
        total_mismatch = employee["overdue_total"] != expected["overdue_total"]
        corrected = bool(missed or total_mismatch)
        return {
            "data_source": source,
            "table": self.finance_repository.table,
            "rows_reviewed": len(invoices),
            "employee_analysis": employee,
            "manager_review": {
                "status": "correction_required" if corrected else "verified",
                "missed_invoice_ids": [row["invoice_id"] for row in missed],
                "expected_overdue_total": expected["overdue_total"],
                "reported_overdue_total": employee["overdue_total"],
                "reason": (
                    "Manager compared the employee answer to the finance source and found missing overdue invoices."
                    if corrected else "Manager independently verified the employee answer against the finance source."
                ),
            },
            "corrected_analysis": expected,
        }

    @staticmethod
    def _analysis(rows: list[dict[str, Any]]) -> dict[str, Any]:
        priority = min(rows, key=lambda row: row["due_date"])
        return {
            "invoice_ids": [row["invoice_id"] for row in rows],
            "overdue_total": round(sum(row["amount"] for row in rows), 2),
            "highest_priority_invoice": priority["invoice_id"],
            "recommendation": (
                f"Contact {priority['customer_name']} about {priority['invoice_id']} first; "
                "it is the oldest overdue invoice."
            ),
        }
