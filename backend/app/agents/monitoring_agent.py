from __future__ import annotations

import time

from backend.app.core.models import ArchitectureState, HealthResult
from backend.app.infrastructure.mock_system import MockSystem
from backend.app.infrastructure.tool_runtime import ToolRuntime


class MonitoringAgent:
    def __init__(self, runtime: ToolRuntime, mock_system: MockSystem):
        self.runtime = runtime
        self.mock_system = mock_system

    async def check(self, architecture: ArchitectureState) -> list[HealthResult]:
        results: list[HealthResult] = [
            HealthResult(id="manager", kind="manager", name="Manager Agent", status="healthy", latency_ms=2, message="Orchestrator is accepting work."),
        ]
        for endpoint in architecture.endpoints:
            results.append(
                HealthResult(
                    id=endpoint.id,
                    kind="endpoint",
                    name=endpoint.name,
                    status=endpoint.status,
                    latency_ms=endpoint.latency_ms,
                    message="Endpoint contract is reachable." if endpoint.status == "healthy" else "Endpoint requires attention.",
                )
            )
        for tool in architecture.tools:
            started = time.perf_counter()
            status = tool.status
            message = "Registered tool is available."
            if tool.generated and tool.source_file:
                try:
                    await self.runtime.execute_file(tool.source_file, tool.probe_input, self.mock_system.get)
                    status = "healthy"
                    message = "Generated tool passed its continuous probe."
                except Exception as exc:
                    status = "offline"
                    message = f"Probe failed: {exc}"
            latency = max(3, round((time.perf_counter() - started) * 1000))
            results.append(HealthResult(id=tool.id, kind="tool", name=tool.name, status=status, latency_ms=latency, message=message))
        return results
