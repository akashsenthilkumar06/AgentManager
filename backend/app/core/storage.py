from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Callable

from backend.app.core.models import (
    AgentConversation,
    AgentRecord,
    ArchitectureState,
    BuildRecord,
    ManagerConversation,
    utc_now,
)
from backend.app.core.seed import demo_architecture


class JsonStore:
    """Tiny, thread-safe metadata store suited to a single-node hackathon demo."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.RLock()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.reset()

    def reset(self) -> dict[str, Any]:
        with self._lock:
            state = {
                "architecture": demo_architecture().model_dump(),
                "builds": [],
                "conversations": [],
                "manager_conversations": [],
                "updated_at": utc_now(),
            }
            self._write(state)
            return state

    def read(self) -> dict[str, Any]:
        with self._lock:
            if not self.path.exists():
                return self.reset()
            return json.loads(self.path.read_text(encoding="utf-8"))

    def architecture(self) -> ArchitectureState:
        data = self.read()["architecture"]
        defaults = {agent.id: agent for agent in demo_architecture().agents}
        for agent in data.get("agents", []):
            fallback = defaults.get(agent.get("id"))
            if fallback is None:
                continue
            if not agent.get("mcp_endpoint"):
                agent["mcp_endpoint"] = fallback.mcp_endpoint
            if not agent.get("features"):
                agent["features"] = fallback.features
            if not agent.get("instructions"):
                agent["instructions"] = fallback.instructions
            if not agent.get("enabled_tools"):
                agent["enabled_tools"] = fallback.enabled_tools
        return ArchitectureState.model_validate(data)

    def builds(self) -> list[BuildRecord]:
        return [BuildRecord.model_validate(item) for item in self.read().get("builds", [])]

    def conversations(self, agent_id: str | None = None) -> list[AgentConversation]:
        conversations = [
            AgentConversation.model_validate(item)
            for item in self.read().get("conversations", [])
        ]
        if agent_id:
            conversations = [item for item in conversations if item.agent_id == agent_id]
        return conversations

    def get_conversation(self, conversation_id: str) -> AgentConversation | None:
        return next(
            (item for item in self.conversations() if item.id == conversation_id),
            None,
        )

    def manager_conversations(self, agent_id: str | None = None) -> list[ManagerConversation]:
        conversations = [
            ManagerConversation.model_validate(item)
            for item in self.read().get("manager_conversations", [])
        ]
        if agent_id:
            conversations = [item for item in conversations if item.agent_id == agent_id]
        return conversations

    def get_manager_conversation(self, conversation_id: str) -> ManagerConversation | None:
        return next(
            (item for item in self.manager_conversations() if item.id == conversation_id),
            None,
        )

    def mutate(self, fn: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
        with self._lock:
            state = self.read()
            fn(state)
            state["updated_at"] = utc_now()
            self._write(state)
            return state

    def upsert_build(self, build: BuildRecord) -> None:
        def update(state: dict[str, Any]) -> None:
            builds = state.setdefault("builds", [])
            item = build.model_dump()
            for index, current in enumerate(builds):
                if current["id"] == build.id:
                    builds[index] = item
                    break
            else:
                builds.insert(0, item)
            del builds[30:]

        self.mutate(update)

    def upsert_conversation(self, conversation: AgentConversation) -> None:
        def update(state: dict[str, Any]) -> None:
            conversations = state.setdefault("conversations", [])
            item = conversation.model_dump()
            for index, current in enumerate(conversations):
                if current["id"] == conversation.id:
                    conversations[index] = item
                    break
            else:
                conversations.insert(0, item)
            conversations.sort(key=lambda current: current["updated_at"], reverse=True)
            del conversations[60:]

        self.mutate(update)

    def upsert_manager_conversation(self, conversation: ManagerConversation) -> None:
        def update(state: dict[str, Any]) -> None:
            conversations = state.setdefault("manager_conversations", [])
            item = conversation.model_dump()
            for index, current in enumerate(conversations):
                if current["id"] == conversation.id:
                    conversations[index] = item
                    break
            else:
                conversations.insert(0, item)
            conversations.sort(key=lambda current: current["updated_at"], reverse=True)
            del conversations[80:]

        self.mutate(update)

    def register_tool(self, tool: dict[str, Any]) -> None:
        def update(state: dict[str, Any]) -> None:
            tools = state["architecture"]["tools"]
            tools[:] = [item for item in tools if item["id"] != tool["id"]]
            tools.append(tool)
            state["architecture"]["indexed_at"] = utc_now()

        self.mutate(update)

    def update_agents(self, agents: list[AgentRecord]) -> None:
        def update(state: dict[str, Any]) -> None:
            state["architecture"]["agents"] = [agent.model_dump() for agent in agents]
            state["architecture"]["indexed_at"] = utc_now()

        self.mutate(update)

    def update_agent(self, agent: AgentRecord) -> None:
        def update(state: dict[str, Any]) -> None:
            agents = state["architecture"]["agents"]
            for index, current in enumerate(agents):
                if current["id"] == agent.id:
                    agents[index] = agent.model_dump()
                    state["architecture"]["indexed_at"] = utc_now()
                    return
            raise ValueError("Managed agent not found")

        self.mutate(update)

    def get_tool(self, tool_id: str) -> dict[str, Any] | None:
        for tool in self.read()["architecture"]["tools"]:
            if tool["id"] == tool_id:
                return tool
        return None

    def _write(self, value: dict[str, Any]) -> None:
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(value, indent=2), encoding="utf-8")
        temp.replace(self.path)
