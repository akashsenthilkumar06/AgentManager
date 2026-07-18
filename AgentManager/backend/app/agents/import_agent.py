"""Imports a local agent directory into the managed fleet."""

from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

from backend.app.agents.architecture_agent import ArchitectureAgent
from backend.app.core.models import (
    AgentImportRequest,
    AgentRecord,
    ConnectedWorkspace,
    utc_now,
)
from backend.app.core.storage import JsonStore
from backend.app.infrastructure.agent_process import AgentProcessManager
from backend.app.infrastructure.managed_workspace import ManagedAgentWorkspace
from backend.app.infrastructure.workspace_access import WorkspaceAccess


class ImportAgent:
    def __init__(
        self,
        store: JsonStore,
        architecture_agent: ArchitectureAgent,
        workspace_access: WorkspaceAccess,
        managed_workspace: ManagedAgentWorkspace,
        process_manager: AgentProcessManager,
    ):
        self.store = store
        self.architecture_agent = architecture_agent
        self.workspace_access = workspace_access
        self.managed_workspace = managed_workspace
        self.process_manager = process_manager

    async def import_directory(
        self,
        request: AgentImportRequest,
    ) -> dict[str, object]:
        root = self.workspace_access.validate_root(Path(request.path))
        profile = self.workspace_access.inspect_agent_project(root)
        existing = next(
            (
                agent
                for agent in self.store.architecture().agents
                if agent.workspace_root
                and Path(agent.workspace_root).resolve() == root
            ),
            None,
        )
        if existing:
            return {
                "agent": existing.model_dump(),
                "workspace": self._workspace(existing).model_dump(),
                "profile": profile,
                "process": self.process_manager.status(existing.id),
                "already_imported": True,
            }

        entrypoints = list(profile["detected_entrypoints"])
        run_command = request.run_command or (
            entrypoints[0] if entrypoints else None
        )
        if request.start_after_import and not run_command:
            raise ValueError(
                "No run command was provided or detected for this directory"
            )
        architecture = self.store.architecture()
        agent_id = self._unique_id(
            request.name or root.name,
            {agent.id for agent in architecture.agents},
        )
        workspace = ConnectedWorkspace(
            id=f"workspace_{uuid4().hex[:10]}",
            name=request.name or root.name,
            root_path=str(root),
            agent_id=agent_id,
            writable=False,
        )
        description = (
            request.description
            or str(profile.get("description") or "")
            or (
                f"Imported local agent workspace with "
                f"{profile['indexed_files']} indexed source files."
            )
        )
        instructions = (
            str(profile.get("instructions") or "")
            or (
                "Use the connected local workspace as source context. "
                "Inspect relevant files before proposing changes, preserve "
                "the project's existing architecture, and verify edits "
                "against its detected runtime."
            )
        )
        languages = list(profile.get("languages", []))
        features = [
            f"Connected source · {profile['indexed_files']} files",
            *[f"{language.title()} project" for language in languages[:4]],
        ]
        endpoint = request.mcp_endpoint or profile.get("mcp_endpoint")
        agent = AgentRecord(
            id=agent_id,
            name=request.name or root.name.replace("-", " ").title(),
            description=description[:500],
            owner=request.owner,
            status="degraded",
            mcp_endpoint=str(endpoint) if endpoint else None,
            features=features,
            instructions=instructions[:4000],
            imported=True,
            workspace_id=workspace.id,
            workspace_root=str(root),
            run_command=run_command,
            detected_entrypoints=entrypoints,
        )
        self.store.update_agents([*architecture.agents, agent])
        self.store.upsert_connected_workspace(workspace)
        if agent.mcp_endpoint:
            try:
                agent = await self.architecture_agent.discover_agent(
                    agent,
                    self.store.architecture(),
                )
                self.store.update_agent(agent)
            except Exception:
                agent = agent.model_copy(update={"status": "degraded"})
                self.store.update_agent(agent)
        self.managed_workspace.sync(agent)

        process = self.process_manager.status(agent.id)
        if request.start_after_import and run_command:
            try:
                process = self.process_manager.start(
                    agent.id,
                    run_command,
                    root,
                )
            except (OSError, ValueError) as exc:
                process = {
                    **self.process_manager.status(agent.id),
                    "status": "failed",
                    "error": str(exc),
                }
        return {
            "agent": agent.model_dump(),
            "workspace": workspace.model_dump(),
            "profile": profile,
            "process": process,
            "already_imported": False,
        }

    def _workspace(self, agent: AgentRecord) -> ConnectedWorkspace:
        workspace = self.store.get_connected_workspace(
            agent.workspace_id or ""
        )
        if workspace is None:
            raise ValueError("Imported agent workspace is missing")
        return workspace

    @staticmethod
    def _unique_id(name: str, existing: set[str]) -> str:
        base = re.sub(
            r"[^a-z0-9]+",
            "-",
            name.lower(),
        ).strip("-") or "imported-agent"
        candidate = base
        suffix = 2
        while candidate in existing:
            candidate = f"{base}-{suffix}"
            suffix += 1
        return candidate
