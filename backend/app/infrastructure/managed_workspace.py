"""Small editable workspaces representing managed/client agents."""

from __future__ import annotations

import json
from pathlib import Path

from backend.app.core.models import AgentRecord
from backend.app.core.storage import JsonStore


class ManagedAgentWorkspace:
    """Persists each managed agent as an independently inspectable file sector."""

    def __init__(self, store: JsonStore):
        self.store = store

    @property
    def root(self) -> Path:
        return self.store.path.parent / "managed_workspaces"

    def initialize(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        for agent in self.store.architecture().agents:
            self.sync(agent)

    def sync(self, agent: AgentRecord) -> None:
        directory = self.root / agent.id
        directory.mkdir(parents=True, exist_ok=True)
        self._write(
            directory / "agent.json",
            json.dumps(
                {
                    "id": agent.id,
                    "name": agent.name,
                    "description": agent.description,
                    "owner": agent.owner,
                    "features": agent.features,
                    "response_style": agent.response_style,
                    "tool_policy": agent.tool_policy,
                    "verification_mode": agent.verification_mode,
                    "memory_enabled": agent.memory_enabled,
                },
                indent=2,
            )
            + "\n",
        )
        self._write(directory / "instructions.md", agent.instructions.strip() + "\n")
        self._write(
            directory / "tools.json",
            json.dumps(
                {
                    "mcp_endpoint": agent.mcp_endpoint,
                    "enabled_tools": agent.enabled_tools,
                    "discovered_tools": [
                        tool.model_dump() for tool in agent.mcp_tools
                    ],
                },
                indent=2,
            )
            + "\n",
        )

    def inspect(self, agent: AgentRecord) -> dict[str, object]:
        self.sync(agent)
        directory = self.root / agent.id
        return {
            "workspace": str(directory),
            "files": [
                {
                    "path": path.name,
                    "size": path.stat().st_size,
                    "preview": path.read_text(encoding="utf-8")[:1200],
                }
                for path in sorted(directory.glob("*"))
                if path.is_file()
            ],
        }

    def apply_instructions(self, agent: AgentRecord, instructions: str) -> AgentRecord:
        updated = agent.model_copy(update={"instructions": instructions.strip()})
        self.store.update_agent(updated)
        self.sync(updated)
        return updated

    @staticmethod
    def _write(path: Path, content: str) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
