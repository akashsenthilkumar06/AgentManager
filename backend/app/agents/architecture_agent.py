from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from typing import Literal

from backend.app.core.models import (
    AgentRecord,
    ArchitectureState,
    MCPToolCapability,
    ReuseCandidate,
    ToolRecord,
)
from backend.app.infrastructure.mcp_client import ManagedAgentMCPClient


ALIASES = {
    "order": {"orders", "commerce", "purchase", "fulfillment"},
    "shipment": {"shipments", "shipping", "delivery", "carrier", "tracking", "logistics", "delay", "delays"},
    "inventory": {"inventory", "stock", "availability", "sku", "catalog"},
    "customer": {"customers", "profile", "support", "shopper"},
    "summary": {"summarize", "summary", "explain", "brief"},
}

CAPABILITY_STOP_WORDS = {
    "agent",
    "and",
    "any",
    "build",
    "capability",
    "check",
    "combine",
    "combines",
    "concise",
    "create",
    "current",
    "detail",
    "details",
    "each",
    "existing",
    "exposure",
    "fleet",
    "for",
    "from",
    "identifies",
    "into",
    "make",
    "new",
    "please",
    "requested",
    "return",
    "returns",
    "that",
    "the",
    "this",
    "tool",
    "using",
    "with",
}

CONCEPT_NORMALIZATION = {
    "available": "availability",
    "availability": "availability",
    "delayed": "delay",
    "delays": "delay",
    "deliveries": "delivery",
    "inventories": "inventory",
    "orders": "order",
    "shipments": "shipment",
    "summaries": "summary",
    "summarize": "summary",
    "summarizes": "summary",
    "tracking": "shipment",
}


@dataclass(slots=True)
class CapabilityMatch:
    capability: MCPToolCapability
    tool: ToolRecord
    relation: Literal["equivalent", "overlap"]
    score: float
    source_agent_ids: list[str]
    reason: str


@dataclass(slots=True)
class FleetCapabilityRelationship:
    kind: Literal["duplicate", "conflict"]
    left_key: str
    right_key: str
    left_name: str
    right_name: str
    agent_ids: list[str]
    score: float
    reason: str


class ArchitectureAgent:
    def __init__(self, mcp_client: ManagedAgentMCPClient):
        self.mcp_client = mcp_client

    async def discover_agent(self, agent: AgentRecord, architecture: ArchitectureState) -> AgentRecord:
        discovery = await self.mcp_client.discover(agent, architecture.tools)
        merged_tools = list(discovery.tools)
        discovered_names = {tool.name for tool in merged_tools}
        for attached in agent.attached_tools:
            if attached.name not in discovered_names:
                merged_tools.append(attached)
                discovered_names.add(attached.name)
        enabled_tools = [
            name for name in agent.enabled_tools if name in discovered_names
        ]
        if merged_tools and not enabled_tools:
            enabled_tools = [tool.name for tool in merged_tools]
        return agent.model_copy(update={
            "mcp_server_name": discovery.server_name,
            "mcp_tools": merged_tools,
            "mcp_prompts": discovery.prompts,
            "mcp_resources": discovery.resources,
            "features": discovery.features or agent.features,
            "enabled_tools": enabled_tools,
            "last_discovered_at": discovery.discovered_at,
            "status": "healthy",
        })

    def find_capability_match(
        self,
        prompt: str,
        architecture: ArchitectureState,
    ) -> CapabilityMatch | None:
        """Find a capability that already covers most of a requested behavior.

        The match is intentionally conservative: complementary primitives remain
        reusable planning context, but only capabilities covering at least 65%
        of the request's meaningful concepts prevent a new build.
        """

        requested = self._capability_concepts(prompt)
        if not requested:
            return None

        candidates = self._fleet_capabilities(architecture)

        matches: list[CapabilityMatch] = []
        for capability, tool, source_agents in candidates.values():
            provided = self._capability_concepts(
                " ".join(
                    [
                        tool.id,
                        capability.name,
                        capability.description,
                        json.dumps(capability.input_schema, sort_keys=True),
                        json.dumps(tool.output_schema, sort_keys=True),
                    ]
                )
            )
            overlap = requested.intersection(provided)
            if not overlap:
                continue
            coverage = len(overlap) / len(requested)
            specificity = len(overlap) / max(
                1,
                min(len(requested), len(provided)),
            )
            score = round(coverage * 0.8 + specificity * 0.2, 2)
            enough_concepts = len(overlap) >= 2 or len(requested) == 1
            required_semantics = {"summary", "risk"}.intersection(requested)
            if not enough_concepts or coverage < 0.65:
                continue
            if not required_semantics.issubset(provided):
                continue
            relation: Literal["equivalent", "overlap"] = (
                "equivalent" if coverage >= 0.85 else "overlap"
            )
            matches.append(
                CapabilityMatch(
                    capability=capability,
                    tool=tool,
                    relation=relation,
                    score=score,
                    source_agent_ids=sorted(source_agents),
                    reason=(
                        f"{relation.title()} fleet capability matched "
                        f"{len(overlap)}/{len(requested)} requested concepts: "
                        f"{', '.join(sorted(overlap))}."
                    ),
                )
            )

        if not matches:
            return None
        matches.sort(
            key=lambda item: (
                item.relation == "equivalent",
                item.score,
                bool(item.source_agent_ids),
            ),
            reverse=True,
        )
        return matches[0]

    def fleet_capability_relationships(
        self,
        architecture: ArchitectureState,
    ) -> list[FleetCapabilityRelationship]:
        """Find independently configured tools that duplicate or conflict."""

        candidates = list(self._fleet_capabilities(architecture).items())
        relationships: list[FleetCapabilityRelationship] = []
        for index, (
            left_key,
            (left_capability, left_tool, left_agents),
        ) in enumerate(candidates):
            for (
                right_key,
                (right_capability, right_tool, right_agents),
            ) in candidates[index + 1:]:
                left_name = self._normalized_tool_name(
                    left_capability.name
                )
                right_name = self._normalized_tool_name(
                    right_capability.name
                )
                same_name = left_name == right_name
                left_schema = self._input_contract(
                    left_capability.input_schema
                )
                right_schema = self._input_contract(
                    right_capability.input_schema
                )
                left_concepts = self._relationship_concepts(
                    left_capability
                )
                right_concepts = self._relationship_concepts(
                    right_capability
                )
                overlap = left_concepts.intersection(right_concepts)
                semantic_score = len(overlap) / max(
                    1,
                    min(len(left_concepts), len(right_concepts)),
                )
                semantically_close = (
                    len(overlap) >= 2 and semantic_score >= 0.8
                )
                if not same_name and not semantically_close:
                    continue

                same_contract = left_schema == right_schema
                kind: Literal["duplicate", "conflict"] = (
                    "duplicate" if same_contract else "conflict"
                )
                if same_name:
                    reason = (
                        f"Independent tools share the name "
                        f"{left_capability.name} and "
                        + (
                            "the same input contract."
                            if same_contract
                            else "different input contracts."
                        )
                    )
                    score = 1.0
                else:
                    reason = (
                        f"{left_capability.name} and "
                        f"{right_capability.name} overlap on "
                        f"{', '.join(sorted(overlap))}; "
                        + (
                            "their input contracts are equivalent."
                            if same_contract
                            else "their input contracts differ."
                        )
                    )
                    score = round(semantic_score, 2)
                relationships.append(
                    FleetCapabilityRelationship(
                        kind=kind,
                        left_key=left_key,
                        right_key=right_key,
                        left_name=left_tool.name,
                        right_name=right_tool.name,
                        agent_ids=sorted(left_agents | right_agents),
                        score=score,
                        reason=reason,
                    )
                )
        return relationships

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

    @staticmethod
    def _capability_concepts(value: str) -> set[str]:
        concepts: set[str] = set()
        for word in re.findall(r"[a-z0-9]+", value.lower()):
            if len(word) <= 2 or word in CAPABILITY_STOP_WORDS:
                continue
            normalized = CONCEPT_NORMALIZATION.get(word, word)
            if normalized.endswith("s") and len(normalized) > 4:
                normalized = normalized[:-1]
            if normalized in CAPABILITY_STOP_WORDS:
                continue
            concepts.add(normalized)
        return concepts

    def _fleet_capabilities(
        self,
        architecture: ArchitectureState,
    ) -> dict[
        str,
        tuple[MCPToolCapability, ToolRecord, set[str]],
    ]:
        candidates: dict[
            str,
            tuple[MCPToolCapability, ToolRecord, set[str]],
        ] = {}
        registered = {tool.id: tool for tool in architecture.tools}
        for tool in architecture.tools:
            capability = MCPToolCapability(
                name=tool.name,
                description=tool.description,
                input_schema=tool.input_schema,
                tool_id=tool.id,
                provider="manager_runtime",
            )
            agents = {
                agent.id
                for agent in architecture.agents
                if tool.id in agent.tool_ids
                or any(
                    attached.tool_id == tool.id
                    for attached in agent.attached_tools
                )
                or any(
                    item.tool_id == tool.id
                    for item in agent.mcp_tools
                )
            }
            candidates[f"tool:{tool.id}"] = (
                capability,
                tool,
                agents,
            )

        for agent in architecture.agents:
            for capability in agent.mcp_tools:
                if capability.tool_id and capability.tool_id in registered:
                    current = candidates.get(
                        f"tool:{capability.tool_id}"
                    )
                    if current:
                        current[2].add(agent.id)
                    continue
                provider_endpoint = (
                    capability.provider_endpoint or agent.mcp_endpoint
                )
                key = (
                    f"mcp:{provider_endpoint}:{capability.name}"
                    if provider_endpoint
                    else f"agent:{agent.id}:{capability.name}"
                )
                if key in candidates:
                    candidates[key][2].add(agent.id)
                    continue
                synthetic_id = "mcp_" + re.sub(
                    r"[^a-z0-9]+",
                    "_",
                    f"{agent.id}_{capability.name}".lower(),
                ).strip("_")
                tool = ToolRecord(
                    id=synthetic_id,
                    name=capability.name,
                    description=capability.description,
                    owner=agent.name,
                    input_schema=capability.input_schema,
                    output_schema={
                        "type": "object",
                        "properties": {},
                    },
                    operation="remote_mcp",
                )
                candidates[key] = (
                    capability.model_copy(
                        update={
                            "provider_endpoint": provider_endpoint,
                        }
                    ),
                    tool,
                    {agent.id},
                )
        return candidates

    def _relationship_concepts(
        self,
        capability: MCPToolCapability,
    ) -> set[str]:
        properties = capability.input_schema.get("properties", {})
        property_names = (
            properties.keys()
            if isinstance(properties, dict)
            else []
        )
        return self._capability_concepts(
            " ".join(
                [
                    capability.name,
                    capability.description,
                    *property_names,
                ]
            )
        )

    @staticmethod
    def _normalized_tool_name(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")

    @staticmethod
    def _input_contract(schema: dict[str, object]) -> str:
        return json.dumps(schema, sort_keys=True, separators=(",", ":"))
