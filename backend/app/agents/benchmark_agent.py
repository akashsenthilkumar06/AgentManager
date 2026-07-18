"""Paired capability benchmarks for unmanaged and managed agent states."""

from __future__ import annotations

import time
from typing import Any, Awaitable, Callable
from uuid import uuid4

from backend.app.core.models import (
    AgentRecord,
    BenchmarkMetric,
    BenchmarkRun,
    BenchmarkScenarioResult,
    BenchmarkSideResult,
    MCPToolCapability,
    ToolRecord,
)
from backend.app.core.seed import demo_architecture
from backend.app.core.storage import JsonStore
from backend.app.infrastructure.mcp_client import ManagedAgentMCPClient


RegisteredToolExecutor = Callable[
    [str, dict[str, Any]],
    Awaitable[dict[str, Any]],
]
LiveAgentPreparer = Callable[[str], Awaitable[AgentRecord]]


class BenchmarkAgent:
    """Runs the same real tool probes against baseline and managed configs."""

    def __init__(
        self,
        store: JsonStore,
        mcp_client: ManagedAgentMCPClient,
        registered_tool_executor: RegisteredToolExecutor,
        live_agent_preparer: LiveAgentPreparer | None = None,
    ):
        self.store = store
        self.mcp_client = mcp_client
        self.registered_tool_executor = registered_tool_executor
        self.live_agent_preparer = live_agent_preparer

    async def run(self, agent_id: str) -> BenchmarkRun:
        architecture = self.store.architecture()
        managed = next(
            (agent for agent in architecture.agents if agent.id == agent_id),
            None,
        )
        if managed is None:
            raise ValueError("Managed agent not found")
        readiness_note: str | None = None
        if (
            self.live_agent_preparer is not None
            and managed.mcp_endpoint
            and managed.mcp_endpoint.startswith(("http://", "https://"))
        ):
            try:
                managed = await self.live_agent_preparer(managed.id)
                readiness_note = (
                    "Agent Manager verified the live MCP boundary and started "
                    "the imported local runtime in the background when needed."
                )
            except Exception as exc:
                readiness_note = (
                    "Agent Manager could not ready the live MCP boundary before "
                    f"the benchmark: {str(exc)[:300]}"
                )
            architecture = self.store.architecture()
        baseline = self._baseline_agent(managed)
        registered = {tool.id: tool for tool in architecture.tools}
        baseline_tools = self._available_tools(
            baseline,
            registered,
        )
        managed_tools = self._available_tools(
            managed,
            registered,
        )
        tool_names = sorted(set(baseline_tools) | set(managed_tools))
        scenarios: list[BenchmarkScenarioResult] = []
        for index, tool_name in enumerate(tool_names):
            baseline_capability = baseline_tools.get(tool_name)
            managed_capability = managed_tools.get(tool_name)
            reference = managed_capability or baseline_capability
            if reference is None:
                continue
            probe_input = self._probe_input(
                reference,
                registered,
            )
            baseline_result = await self._run_side(
                baseline,
                baseline_capability,
                probe_input,
            )
            managed_result = await self._run_side(
                managed,
                managed_capability,
                probe_input,
            )
            scenarios.append(
                BenchmarkScenarioResult(
                    id=f"scenario_{index + 1}",
                    title=reference.description or tool_name,
                    objective=(
                        f"Execute {tool_name} with representative input and "
                        "return grounded structured output."
                    ),
                    required_tool=tool_name,
                    probe_input=probe_input,
                    baseline=baseline_result,
                    managed=managed_result,
                )
            )

        metrics = self._metrics(scenarios)
        baseline_score = self._metric(metrics, "overall_score", "baseline")
        managed_score = self._metric(metrics, "overall_score", "managed")
        delta = round(managed_score - baseline_score, 1)
        if not scenarios:
            summary = (
                "No executable MCP or registered tools are available yet. "
                "Connect or attach capabilities before comparing performance."
            )
        elif delta > 0:
            summary = (
                f"The managed configuration scored {delta:g} points higher "
                "on the same executable capability scenarios."
            )
        elif delta < 0:
            summary = (
                f"The managed configuration scored {abs(delta):g} points "
                "lower; inspect failed or disabled managed tools."
            )
        else:
            summary = (
                "Both configurations performed equally on the current "
                "scenario set; no unsupported uplift is being claimed."
            )
        run = BenchmarkRun(
            id=f"benchmark_{uuid4().hex[:10]}",
            agent_id=managed.id,
            agent_name=managed.name,
            summary=summary,
            metrics=metrics,
            scenarios=scenarios,
            evidence=[
                (
                    f"Compared {len(scenarios)} identical tool scenario"
                    f"{'s' if len(scenarios) != 1 else ''}."
                ),
                (
                    "Manager-runtime tools executed their registered source; "
                    "agent-MCP tools called their configured HTTP endpoint."
                ),
                (
                    "Scores use observed availability, execution success, "
                    "structured grounding, and verification readiness."
                ),
                "No OpenAI call is used by the benchmark runner.",
                *([readiness_note] if readiness_note else []),
            ],
        )
        self.store.upsert_benchmark(run)
        return run

    @staticmethod
    def _baseline_agent(managed: AgentRecord) -> AgentRecord:
        seeded = next(
            (
                agent
                for agent in demo_architecture().agents
                if agent.id == managed.id
            ),
            None,
        )
        if seeded:
            return seeded
        native_tools = [
            tool
            for tool in managed.mcp_tools
            if tool.provider == "agent_mcp"
            and not any(
                attached.name == tool.name
                for attached in managed.attached_tools
            )
        ]
        return managed.model_copy(
            update={
                "attached_tools": [],
                "mcp_tools": native_tools,
                "tool_ids": [],
                "enabled_tools": [tool.name for tool in native_tools],
                "instructions": (
                    "Use the capabilities provided by the original agent "
                    "workspace without Manager-added policy or tools."
                ),
                "verification_mode": "advisory",
            }
        )

    @staticmethod
    def _available_tools(
        agent: AgentRecord,
        registered: dict[str, ToolRecord],
    ) -> dict[str, MCPToolCapability]:
        capabilities = {tool.name: tool for tool in agent.mcp_tools}
        for tool_id in agent.tool_ids:
            tool = registered.get(tool_id)
            if tool and tool.name not in capabilities:
                capabilities[tool.name] = MCPToolCapability(
                    name=tool.name,
                    description=tool.description,
                    input_schema=tool.input_schema,
                    tool_id=tool.id,
                    provider="manager_runtime",
                )
        if agent.tool_policy == "disabled":
            return {}
        if agent.enabled_tools:
            return {
                name: capability
                for name, capability in capabilities.items()
                if name in agent.enabled_tools
            }
        return capabilities

    async def _run_side(
        self,
        agent: AgentRecord,
        capability: MCPToolCapability | None,
        probe_input: dict[str, Any],
    ) -> BenchmarkSideResult:
        if capability is None:
            return BenchmarkSideResult(
                status="unavailable",
                tool_name="not_configured",
                error="Capability is not available in this configuration.",
            )
        started = time.perf_counter()
        try:
            if capability.provider == "manager_runtime":
                if not capability.tool_id:
                    raise ValueError(
                        "Registered capability has no tool identifier"
                    )
                output = await self.registered_tool_executor(
                    capability.tool_id,
                    probe_input,
                )
            else:
                endpoint = (
                    capability.provider_endpoint or agent.mcp_endpoint
                )
                if not endpoint:
                    raise ValueError("Agent MCP endpoint is not configured")
                output = await self.mcp_client.call_tool(
                    endpoint,
                    capability.name,
                    probe_input,
                )
            return BenchmarkSideResult(
                status="passed",
                tool_name=capability.name,
                provider=capability.provider,
                latency_ms=max(
                    1,
                    round((time.perf_counter() - started) * 1000),
                ),
                output_keys=sorted(output),
            )
        except Exception as exc:
            return BenchmarkSideResult(
                status="failed",
                tool_name=capability.name,
                provider=capability.provider,
                latency_ms=max(
                    1,
                    round((time.perf_counter() - started) * 1000),
                ),
                error=str(exc)[:500],
            )

    @staticmethod
    def _probe_input(
        capability: MCPToolCapability,
        registered: dict[str, ToolRecord],
    ) -> dict[str, Any]:
        if capability.tool_id and capability.tool_id in registered:
            probe = registered[capability.tool_id].probe_input
            if probe:
                return probe
        properties = capability.input_schema.get("properties", {})
        if not isinstance(properties, dict):
            return {}
        known = {
            "order_id": "ORD-1042",
            "sku": "SKU-RED-42",
            "ticket_id": "TCK-9001",
            "tracking_number": "1Z83A04",
            "hours": 24,
            "priority": "normal",
        }
        probe: dict[str, Any] = {}
        required = capability.input_schema.get(
            "required",
            list(properties),
        )
        for name in required if isinstance(required, list) else []:
            schema = properties.get(name, {})
            if name in known:
                probe[name] = known[name]
            elif isinstance(schema, dict) and "default" in schema:
                probe[name] = schema["default"]
            elif isinstance(schema, dict) and schema.get("type") == "integer":
                probe[name] = 1
            elif isinstance(schema, dict) and schema.get("type") == "boolean":
                probe[name] = True
            else:
                probe[name] = f"benchmark-{name}"
        return probe

    @classmethod
    def _metrics(
        cls,
        scenarios: list[BenchmarkScenarioResult],
    ) -> list[BenchmarkMetric]:
        count = len(scenarios)

        def values(side: str) -> dict[str, float]:
            results = [getattr(item, side) for item in scenarios]
            available = [
                item for item in results
                if item.status != "unavailable"
            ]
            passed = [item for item in results if item.status == "passed"]
            grounded = [item for item in passed if item.output_keys]
            denominator = max(1, count)
            latency_denominator = max(1, len(available))
            task_success = 100 * len(passed) / denominator
            coverage = 100 * len(available) / denominator
            grounding = 100 * len(grounded) / denominator
            verification = 100 * len(grounded) / denominator
            overall = (
                task_success * 0.35
                + coverage * 0.2
                + grounding * 0.25
                + verification * 0.2
            )
            return {
                "overall_score": round(overall, 1),
                "task_success": round(task_success, 1),
                "tool_coverage": round(coverage, 1),
                "grounding_rate": round(grounding, 1),
                "verification_rate": round(verification, 1),
                "average_latency": round(
                    sum(item.latency_ms for item in available)
                    / latency_denominator,
                    1,
                ),
            }

        baseline = values("baseline")
        managed = values("managed")
        definitions = [
            ("overall_score", "Overall score", "percent", True),
            ("task_success", "Task success", "percent", True),
            ("tool_coverage", "Tool coverage", "percent", True),
            ("grounding_rate", "Grounded output", "percent", True),
            (
                "verification_rate",
                "Verification readiness",
                "percent",
                True,
            ),
            (
                "average_latency",
                "Average tool latency",
                "milliseconds",
                False,
            ),
        ]
        return [
            BenchmarkMetric(
                id=metric_id,
                label=label,
                unit=unit,
                higher_is_better=higher,
                baseline=baseline[metric_id],
                managed=managed[metric_id],
            )
            for metric_id, label, unit, higher in definitions
        ]

    @staticmethod
    def _metric(
        metrics: list[BenchmarkMetric],
        metric_id: str,
        side: str,
    ) -> float:
        metric = next(item for item in metrics if item.id == metric_id)
        return float(getattr(metric, side))
