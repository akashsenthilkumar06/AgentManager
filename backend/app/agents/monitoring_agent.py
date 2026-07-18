from __future__ import annotations

import asyncio
import hashlib
import json
import time
from typing import Any
from uuid import uuid4

from backend.app.agents.architecture_agent import ArchitectureAgent
from backend.app.core.models import (
    AgentRecord,
    ArchitectureState,
    FindingTrigger,
    HealthResult,
    ReconciliationFinding,
    utc_now,
)
from backend.app.core.storage import JsonStore
from backend.app.infrastructure.managed_workspace import (
    ManagedAgentWorkspace,
)
from backend.app.infrastructure.mock_system import MockSystem
from backend.app.infrastructure.tool_runtime import ToolRuntime


class MonitoringAgent:
    def __init__(
        self,
        runtime: ToolRuntime,
        mock_system: MockSystem,
        store: JsonStore,
        architecture_agent: ArchitectureAgent,
        managed_workspace: ManagedAgentWorkspace,
    ):
        self.runtime = runtime
        self.mock_system = mock_system
        self.store = store
        self.architecture_agent = architecture_agent
        self.managed_workspace = managed_workspace
        self._reconcile_lock = asyncio.Lock()

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

    async def reconcile_once(self) -> dict[str, Any]:
        async with self._reconcile_lock:
            return await self._reconcile_once()

    async def _reconcile_once(self) -> dict[str, Any]:
        """Re-observe the fleet and record changes without invoking an LLM."""

        checked_at = utc_now()
        previous = self.store.reconciliation_snapshot()
        previous_agents = previous.get("agents", {})
        architecture = self.store.architecture()
        discovered_agents: list[AgentRecord] = []
        successful_discoveries: set[str] = set()
        finding_specs: list[dict[str, Any]] = []
        active_keys: set[str] = set()

        for agent in architecture.agents:
            if not agent.mcp_endpoint:
                discovered_agents.append(agent)
                successful_discoveries.add(agent.id)
                continue
            try:
                discovered = await self.architecture_agent.discover_agent(
                    agent,
                    architecture,
                )
                successful_discoveries.add(agent.id)
            except Exception as exc:
                discovered = agent.model_copy(
                    update={"status": "degraded"}
                )
                key = f"endpoint:{agent.id}"
                active_keys.add(key)
                finding_specs.append(
                    {
                        "key": key,
                        "kind": "endpoint_health",
                        "severity": "critical",
                        "status": "open",
                        "title": f"{agent.name} MCP endpoint is failing",
                        "detail": (
                            f"Standing discovery could not refresh "
                            f"{agent.mcp_endpoint or 'the configured endpoint'}: "
                            f"{str(exc)[:500]}"
                        ),
                        "why_it_matters": (
                            "The agent may be operating with stale tool "
                            "contracts, and live calls to its MCP tools can fail."
                        ),
                        "agent_ids": [agent.id],
                        "before": previous_agents.get(agent.id, {}),
                        "after": {
                            "status": "degraded",
                            "endpoint": agent.mcp_endpoint,
                        },
                    }
                )
            discovered_agents.append(discovered)

        latest_agents = {
            agent.id: agent
            for agent in self.store.architecture().agents
        }
        discovered_agents = [
            self._merge_latest_agent(
                discovered,
                latest_agents.get(discovered.id),
            )
            for discovered in discovered_agents
        ]
        self.store.update_agents(discovered_agents)
        for agent in discovered_agents:
            self.managed_workspace.sync(agent)
        architecture = self.store.architecture()
        current_agents = {
            agent.id: self._agent_capability_state(agent)
            for agent in architecture.agents
        }

        if previous_agents:
            for agent in architecture.agents:
                if agent.id not in successful_discoveries:
                    continue
                before = previous_agents.get(agent.id)
                after = current_agents[agent.id]
                if not before:
                    continue
                drift = self._capability_drift(before, after)
                if not drift:
                    continue
                before_hash = self._fingerprint(before)
                after_hash = self._fingerprint(after)
                key = (
                    f"drift:{agent.id}:"
                    f"{before_hash[:10]}:{after_hash[:10]}"
                )
                severity = (
                    "warning"
                    if drift["removed"] or drift["changed"]
                    else "info"
                )
                finding_specs.append(
                    {
                        "key": key,
                        "kind": "capability_drift",
                        "severity": severity,
                        "status": "observed",
                        "title": f"{agent.name} capability drift detected",
                        "detail": self._drift_detail(drift),
                        "why_it_matters": (
                            "Fleet plans and live tool selection should use "
                            "the new contract instead of the previous snapshot."
                        ),
                        "agent_ids": [agent.id],
                        "tool_names": sorted(
                            {
                                *drift["added"],
                                *drift["removed"],
                                *drift["changed"],
                            }
                        ),
                        "before": before,
                        "after": after,
                    }
                )

        for relationship in (
            self.architecture_agent.fleet_capability_relationships(
                architecture
            )
        ):
            left, right = sorted(
                [relationship.left_key, relationship.right_key]
            )
            key = f"relationship:{relationship.kind}:{left}:{right}"
            active_keys.add(key)
            conflict = relationship.kind == "conflict"
            finding_specs.append(
                {
                    "key": key,
                    "kind": (
                        "capability_conflict"
                        if conflict
                        else "duplicate_capability"
                    ),
                    "severity": "critical" if conflict else "warning",
                    "status": "open",
                    "title": (
                        "Conflicting fleet tool contracts"
                        if conflict
                        else "Duplicate fleet capability detected"
                    ),
                    "detail": relationship.reason,
                    "why_it_matters": (
                        "Agents can select incompatible behavior for the "
                        "same tool identity."
                        if conflict
                        else "Maintaining two independent implementations "
                        "increases drift and makes routing ambiguous."
                    ),
                    "agent_ids": relationship.agent_ids,
                    "tool_names": sorted(
                        {
                            relationship.left_name,
                            relationship.right_name,
                        }
                    ),
                    "after": {
                        "left": relationship.left_key,
                        "right": relationship.right_key,
                        "overlap_score": relationship.score,
                    },
                }
            )

        health_results = await self.check(architecture)
        for result in health_results:
            if result.status == "healthy":
                continue
            key = f"health:{result.kind}:{result.id}"
            active_keys.add(key)
            finding_specs.append(
                {
                    "key": key,
                    "kind": "component_health",
                    "severity": (
                        "critical"
                        if result.status == "offline"
                        else "warning"
                    ),
                    "status": "open",
                    "title": f"{result.name} needs attention",
                    "detail": result.message,
                    "why_it_matters": (
                        "A fleet dependency is not currently meeting its "
                        "registered health contract."
                    ),
                    "tool_names": (
                        [result.name]
                        if result.kind == "tool"
                        else []
                    ),
                    "after": result.model_dump(),
                }
            )

        recorded = [
            self._record_finding(spec, architecture, checked_at)
            for spec in finding_specs
        ]
        self.store.resolve_reconciliation_findings(
            active_keys,
            {
                "duplicate_capability",
                "capability_conflict",
                "endpoint_health",
                "component_health",
            },
            checked_at,
        )
        snapshot = {
            "last_checked_at": checked_at,
            "last_error": None,
            "agents": current_agents,
            "health": {
                f"{item.kind}:{item.id}": item.status
                for item in health_results
            },
            "summary": {
                "agents_scanned": len(architecture.agents),
                "capabilities_scanned": sum(
                    len(agent.mcp_tools)
                    for agent in architecture.agents
                ),
                "active_findings": len(active_keys),
                "findings_observed": len(recorded),
                "token_usage": 0,
            },
        }
        self.store.set_reconciliation_snapshot(snapshot)
        return {
            "checked_at": checked_at,
            "findings": [item.model_dump() for item in recorded],
            "summary": snapshot["summary"],
        }

    async def run_loop(self, interval_seconds: float) -> None:
        """Run standing reconciliation until application shutdown."""

        while True:
            await asyncio.sleep(interval_seconds)
            try:
                await self.reconcile_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                snapshot = self.store.reconciliation_snapshot()
                snapshot.update(
                    {
                        "last_checked_at": utc_now(),
                        "last_error": str(exc)[:500],
                    }
                )
                self.store.set_reconciliation_snapshot(snapshot)

    def _record_finding(
        self,
        spec: dict[str, Any],
        architecture: ArchitectureState,
        observed_at: str,
    ) -> ReconciliationFinding:
        existing = self.store.get_finding(str(spec["key"]))
        trigger = existing.trigger if existing else None
        if existing is None or existing.status == "resolved":
            try:
                matches = self.architecture_agent.search(
                    f"{spec['title']} {spec['detail']}",
                    architecture,
                    limit=5,
                )
                trigger = FindingTrigger(
                    status="completed",
                    detail=(
                        "Anomaly edge triggered ArchitectureAgent review; "
                        f"{len(matches)} related fleet components were mapped "
                        "without an OpenAI call."
                    ),
                    related_component_ids=[
                        item.id for item in matches
                    ],
                )
            except Exception as exc:
                trigger = FindingTrigger(
                    status="failed",
                    detail=(
                        "ArchitectureAgent review trigger failed: "
                        f"{str(exc)[:300]}"
                    ),
                )
        finding = ReconciliationFinding(
            id=f"finding_{uuid4().hex[:10]}",
            detected_at=observed_at,
            last_seen_at=observed_at,
            trigger=trigger,
            **spec,
        )
        return self.store.upsert_finding(finding)

    @staticmethod
    def _merge_latest_agent(
        discovered: AgentRecord,
        latest: AgentRecord | None,
    ) -> AgentRecord:
        """Keep concurrent config/attachment edits while applying discovery."""

        if latest is None:
            return discovered
        merged_tools = list(discovered.mcp_tools)
        known_names = {tool.name for tool in merged_tools}
        for attached in latest.attached_tools:
            if attached.name not in known_names:
                merged_tools.append(attached)
                known_names.add(attached.name)
        enabled_tools = [
            name
            for name in dict.fromkeys(
                [
                    *latest.enabled_tools,
                    *discovered.enabled_tools,
                ]
            )
            if name in known_names
        ]
        return latest.model_copy(
            update={
                "mcp_server_name": discovered.mcp_server_name,
                "mcp_tools": merged_tools,
                "mcp_prompts": discovered.mcp_prompts,
                "mcp_resources": discovered.mcp_resources,
                "features": discovered.features,
                "enabled_tools": enabled_tools,
                "last_discovered_at": discovered.last_discovered_at,
                "status": discovered.status,
            }
        )

    @classmethod
    def _agent_capability_state(
        cls,
        agent: AgentRecord,
    ) -> dict[str, Any]:
        tools = {
            capability.name: {
                "fingerprint": cls._fingerprint(
                    {
                        "description": capability.description,
                        "input_schema": capability.input_schema,
                        "tool_id": capability.tool_id,
                        "provider": capability.provider,
                        "provider_endpoint": (
                            capability.provider_endpoint
                        ),
                    }
                ),
                "provider": capability.provider,
                "tool_id": capability.tool_id,
                "provider_endpoint": capability.provider_endpoint,
            }
            for capability in agent.mcp_tools
        }
        return {
            "endpoint": agent.mcp_endpoint,
            "status": agent.status,
            "tools": tools,
        }

    @staticmethod
    def _capability_drift(
        before: dict[str, Any],
        after: dict[str, Any],
    ) -> dict[str, list[str]] | None:
        before_tools = before.get("tools", {})
        after_tools = after.get("tools", {})
        before_names = set(before_tools)
        after_names = set(after_tools)
        changed = sorted(
            name
            for name in before_names.intersection(after_names)
            if before_tools[name].get("fingerprint")
            != after_tools[name].get("fingerprint")
        )
        drift = {
            "added": sorted(after_names - before_names),
            "removed": sorted(before_names - after_names),
            "changed": changed,
        }
        return drift if any(drift.values()) else None

    @staticmethod
    def _drift_detail(drift: dict[str, list[str]]) -> str:
        parts: list[str] = []
        for label in ("added", "removed", "changed"):
            if drift[label]:
                parts.append(
                    f"{label.title()}: {', '.join(drift[label])}"
                )
        return ". ".join(parts) + "."

    @staticmethod
    def _fingerprint(value: Any) -> str:
        serialized = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
