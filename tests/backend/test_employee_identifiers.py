"""Identifier extraction must never silently substitute another record."""

from __future__ import annotations

import asyncio

from backend.app.agents.employees.coding_employee import run as run_coding
from backend.app.agents.employees.finance_employee import run as run_finance
from backend.app.agents.employees.support_employee import run as run_support
from backend.app.infrastructure.cloud_data import CloudDataConnector
from backend.app.infrastructure.mock_system import MockSystem


def test_deterministic_employees_use_the_identifier_in_the_request():
    system = CloudDataConnector(MockSystem())

    finance = asyncio.run(
        run_finance(system, "What is the status of INV-1120?")
    )
    support = asyncio.run(
        run_support(system, "What happened to TCK-9012?")
    )
    coding = asyncio.run(
        run_coding(system, "Review REPO-1 before release.")
    )

    assert finance["inputs"]["invoice_id"] == "INV-1120"
    assert support["inputs"]["ticket_id"] == "TCK-9012"
    assert coding["inputs"]["repo_id"] == "REPO-1"
