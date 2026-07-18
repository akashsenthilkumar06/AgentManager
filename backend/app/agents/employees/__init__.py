from __future__ import annotations

from typing import Any, Awaitable, Callable

from backend.app.agents.employees.coding_employee import (
    AGENT_ID as CODING_AGENT_ID,
    REQUIRED_TOOL as CODING_REQUIRED_TOOL,
    run as run_coding_employee,
)
from backend.app.agents.employees.finance_employee import (
    AGENT_ID as FINANCE_AGENT_ID,
    REQUIRED_TOOL as FINANCE_REQUIRED_TOOL,
    run as run_finance_employee,
)
from backend.app.agents.employees.support_employee import (
    AGENT_ID as SUPPORT_AGENT_ID,
    REQUIRED_TOOL as SUPPORT_REQUIRED_TOOL,
    run as run_support_employee,
)
from backend.app.infrastructure.mock_system import MockSystem


EmployeeRunner = Callable[[MockSystem, str], Awaitable[dict[str, Any]]]

REQUIRED_TOOLS: dict[str, tuple[str, str]] = {
    FINANCE_AGENT_ID: FINANCE_REQUIRED_TOOL,
    CODING_AGENT_ID: CODING_REQUIRED_TOOL,
    SUPPORT_AGENT_ID: SUPPORT_REQUIRED_TOOL,
}

EMPLOYEE_HANDLERS: dict[str, EmployeeRunner] = {
    FINANCE_AGENT_ID: run_finance_employee,
    CODING_AGENT_ID: run_coding_employee,
    SUPPORT_AGENT_ID: run_support_employee,
}
