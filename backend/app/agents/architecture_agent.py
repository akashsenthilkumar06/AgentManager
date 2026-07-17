from __future__ import annotations

import re
from collections import Counter

from backend.app.core.models import AgentRecord, ArchitectureState, ReuseCandidate
from backend.app.infrastructure.mcp_client import ManagedAgentMCPClient


ALIASES = {
    "order": {"orders", "commerce", "purchase", "fulfillment"},
    "shipment": {"shipments", "shipping", "delivery", "carrier", "tracking", "logistics", "delay", "delays"},
    "inventory": {"inventory", "stock", "availability", "sku", "catalog"},
    "customer": {"customers", "profile", "support", "shopper"},
    "summary": {"summarize", "summary", "explain", "brief"},
}


class ArchitectureAgent:
    def __init__(self, mcp_client: ManagedAgentMCPClient):
        self.mcp_client = mcp_client

    async def discover_agent(self, agent: AgentRecord, architecture: ArchitectureState) -> AgentRecord:
        discovery = await self.mcp_client.discover(agent, architecture.tools)
        discovered_names = {tool.name for tool in discovery.tools}
        enabled_tools = [
            name for name in agent.enabled_tools if name in discovered_names
        ]
        if discovery.tools and not enabled_tools:
            enabled_tools = [tool.name for tool in discovery.tools]
        return agent.model_copy(update={
            "mcp_server_name": discovery.server_name,
            "mcp_tools": discovery.tools,
            "mcp_prompts": discovery.prompts,
            "mcp_resources": discovery.resources,
            "features": discovery.features or agent.features,
            "enabled_tools": enabled_tools,
            "last_discovered_at": discovery.discovered_at,
            "status": "healthy",
        })

    async def discover_all(self, architecture: ArchitectureState) -> list[AgentRecord]:
        discovered: list[AgentRecord] = []
        for agent in architecture.agents:
            try:
                discovered.append(await self.discover_agent(agent, architecture))
            except Exception:
                discovered.append(agent.model_copy(update={"status": "degraded"}))
        return discovered

    def search(self, prompt: str, architecture: ArchitectureState, limit: int = 8) -> list[ReuseCandidate]:
        query = self._terms(prompt)
        expanded = set(query)
        for term in query:
            for root, aliases in ALIASES.items():
                if term == root or term in aliases:
                    expanded.add(root)
                    expanded.update(aliases)

        results: list[ReuseCandidate] = []
        groups = [
            ("tool", architecture.tools),
            ("endpoint", architecture.endpoints),
            ("data_source", architecture.data_sources),
            ("agent", architecture.agents),
        ]
        for kind, records in groups:
            for record in records:
                searchable = " ".join(
                    str(value)
                    for value in [
                        record.id,
                        record.name,
                        record.description,
                        getattr(record, "owner", ""),
                        " ".join(getattr(record, "tags", [])),
                        " ".join(getattr(record, "features", [])),
                    ]
                )
                terms = self._terms(searchable)
                overlap = expanded.intersection(terms)
                if not overlap:
                    continue
                weighted = sum(2 if term in query else 1 for term in overlap)
                score = min(0.99, 0.30 + weighted / max(8, len(expanded)))
                results.append(
                    ReuseCandidate(
                        kind=kind,
                        id=record.id,
                        name=record.name,
                        description=record.description,
                        score=round(score, 2),
                        reason=f"Matched {', '.join(sorted(overlap)[:4])}",
                    )
                )
        kind_priority = {"endpoint": 3, "tool": 2, "data_source": 1, "agent": 0}
        results.sort(key=lambda item: (item.score, kind_priority[item.kind]), reverse=True)
        return results[:limit]

    def summary(self, architecture: ArchitectureState) -> dict[str, object]:
        statuses = Counter(
            record.status
            for group in [architecture.agents, architecture.tools, architecture.endpoints, architecture.data_sources]
            for record in group
        )
        return {
            "counts": {
                "agents": len(architecture.agents),
                "tools": len(architecture.tools),
                "endpoints": len(architecture.endpoints),
                "data_sources": len(architecture.data_sources),
            },
            "statuses": dict(statuses),
            "indexed_at": architecture.indexed_at,
        }

    @staticmethod
    def _terms(value: str) -> set[str]:
        words = re.findall(r"[a-z0-9]+", value.lower())
        stop = {"a", "an", "and", "the", "that", "to", "for", "from", "with", "of", "is", "it", "new", "tool", "api"}
        return {word for word in words if len(word) > 2 and word not in stop}
