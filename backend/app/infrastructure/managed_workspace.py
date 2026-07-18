"""Small editable workspaces representing managed/client agents."""

from __future__ import annotations

import json
from pathlib import Path

from backend.app.core.models import AgentRecord, ConnectedWorkspace
from backend.app.core.storage import JsonStore
from backend.app.infrastructure.workspace_access import WorkspaceAccess


class ManagedAgentWorkspace:
    """Persists each managed agent as an independently inspectable file sector."""

    def __init__(
        self,
        store: JsonStore,
        workspace_access: WorkspaceAccess,
    ):
        self.store = store
        self.workspace_access = workspace_access

    @property
    def root(self) -> Path:
        return self.store.path.parent / "managed_workspaces"

    def initialize(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        for agent in self.store.architecture().agents:
            if agent.imported and agent.workspace_id:
                connected = self.store.get_connected_workspace(
                    agent.workspace_id
                )
                if connected is not None and not connected.writable:
                    self.store.upsert_connected_workspace(
                        connected.model_copy(update={"writable": True})
                    )
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
                    "openai_model": agent.openai_model,
                    "openai_reasoning_effort": (
                        agent.openai_reasoning_effort
                    ),
                    "imported": agent.imported,
                    "workspace_id": agent.workspace_id,
                    "workspace_root": agent.workspace_root,
                    "run_command": agent.run_command,
                    "detected_entrypoints": agent.detected_entrypoints,
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
                    "attached_tools": [
                        tool.model_dump() for tool in agent.attached_tools
                    ],
                    "discovered_tools": [
                        tool.model_dump() for tool in agent.mcp_tools
                    ],
                },
                indent=2,
            )
            + "\n",
        )

    def inspect(
        self,
        agent: AgentRecord,
        query: str = "",
    ) -> dict[str, object]:
        self.sync(agent)
        directory = self.root / agent.id
        result: dict[str, object] = {
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
        connected = next(
            (
                workspace
                for workspace in self.store.connected_workspaces()
                if workspace.agent_id == agent.id
            ),
            None,
        )
        if connected is None:
            return result
        root = self.workspace_access.validate_root(
            Path(connected.root_path)
        )
        matches = self.workspace_access.search(
            query or agent.description,
            limit=12,
            root=root,
        )
        context_files = []
        for match in matches:
            try:
                content = self.workspace_access.read_file(
                    match.path,
                    root=root,
                )
            except (FileNotFoundError, PermissionError):
                continue
            context_files.append(
                {
                    **match.model_dump(),
                    "language": content.language,
                    "content": content.content,
                    "truncated": content.truncated,
                }
            )
        result["connected_workspace"] = {
            **connected.model_dump(),
            **self.workspace_access.summary(root),
            "read_only": not connected.writable,
        }
        result["context_files"] = context_files
        return result

    def write_file(
        self,
        agent: AgentRecord,
        relative_path: str,
        content: str,
    ) -> dict[str, object]:
        connected, root = self._writable_workspace(agent)
        result = self.workspace_access.write_text_file(
            relative_path,
            content,
            root=root,
        )
        return {
            **result,
            "agent_id": agent.id,
            "workspace_id": connected.id,
            "workspace_root": str(root),
            "writable": True,
        }

    async def run_python_file(
        self,
        agent: AgentRecord,
        relative_path: str,
    ) -> dict[str, object]:
        connected, root = self._writable_workspace(agent)
        result = await self.workspace_access.run_python_file(
            relative_path,
            root=root,
        )
        return {
            **result,
            "agent_id": agent.id,
            "workspace_id": connected.id,
            "workspace_root": str(root),
        }

    def apply_instructions(self, agent: AgentRecord, instructions: str) -> AgentRecord:
        updated = agent.model_copy(update={"instructions": instructions.strip()})
        self.store.update_agent(updated)
        self.sync(updated)
        return updated

    def _writable_workspace(
        self,
        agent: AgentRecord,
    ) -> tuple[ConnectedWorkspace, Path]:
        if not agent.imported or not agent.workspace_id:
            raise ValueError(
                "Source-file operations require an imported local agent"
            )
        connected = self.store.get_connected_workspace(agent.workspace_id)
        if connected is None:
            raise ValueError("Imported agent workspace is missing")
        if not connected.writable:
            raise PermissionError(
                "This connected workspace is not enabled for file writes"
            )
        root = self.workspace_access.validate_root(
            Path(connected.root_path)
        )
        return connected, root

    @staticmethod
    def _write(path: Path, content: str) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
