"""Credential-scoped data connector for employee-agent demonstrations.

The connector makes the manager's data access explicit: employee agents receive
only the response, while the tool record identifies whether it came from a
configured cloud API or the local demo dataset. It never discovers, forwards,
or accepts another agent's credentials.
"""

from __future__ import annotations

from typing import Any

import httpx

from backend.app.infrastructure.mock_system import MockSystem


class CloudDataConnector:
    """Read approved cloud resources, or use transparent local demo data."""

    def __init__(
        self,
        mock_system: MockSystem,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.mock_system = mock_system
        self.base_url = base_url.rstrip("/") if base_url else None
        self.api_key = api_key

    async def get(self, path: str) -> dict[str, Any]:
        if not self.base_url:
            result = await self.mock_system.get(path)
            return {**result, "_data_source": "local-demo-cloud-simulator"}
        if not self.api_key:
            raise PermissionError(
                "AGENT_MANAGER_CLOUD_API_KEY is required when "
                "AGENT_MANAGER_CLOUD_BASE_URL is configured"
            )
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{self.base_url}{path}",
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Cloud API must return a JSON object")
        return {**payload, "_data_source": "configured-cloud-api"}
