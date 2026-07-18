"""Runtime and capability operations for independently managed agents."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Awaitable, Callable

import httpx

from backend.app.agents.architecture_agent import ArchitectureAgent
from backend.app.core.models import AgentRecord
from backend.app.core.storage import JsonStore
from backend.app.infrastructure.agent_process import AgentProcessManager
from backend.app.infrastructure.managed_workspace import ManagedAgentWorkspace
from backend.app.infrastructure.mcp_client import ManagedAgentMCPClient
from backend.app.infrastructure.workspace_access import WorkspaceAccess

RegisteredToolExecutor = Callable[
    [str, dict[str, Any]],
    Awaitable[dict[str, Any]],
]


class ManagedAgentOperator:
    """Runs, discovers, and calls agents through their configured boundaries."""

    def __init__(
        self,
        store: JsonStore,
        architecture_agent: ArchitectureAgent,
        mcp_client: ManagedAgentMCPClient,
        process_manager: AgentProcessManager,
        workspace_access: WorkspaceAccess,
        managed_workspace: ManagedAgentWorkspace,
        registered_tool_executor: RegisteredToolExecutor,
    ):
        self.store = store
        self.architecture_agent = architecture_agent
        self.mcp_client = mcp_client
        self.process_manager = process_manager
        self.workspace_access = workspace_access
        self.managed_workspace = managed_workspace
        self.registered_tool_executor = registered_tool_executor

    def status(self, agent_id: str) -> dict[str, Any]:
        agent = self._agent(agent_id)
        workspace: dict[str, Any] | None = None
        if agent.workspace_root:
            root = self.workspace_access.validate_root(
                Path(agent.workspace_root)
            )
            workspace = self.workspace_access.summary(root)
        return {
            "agent_id": agent.id,
            "agent_name": agent.name,
            "imported": agent.imported,
            "endpoint": agent.mcp_endpoint,
            "server_name": agent.mcp_server_name,
            "tools": [tool.name for tool in agent.mcp_tools],
            "enabled_tools": list(agent.enabled_tools),
            "workspace": workspace,
            "process": self.process_manager.status(agent.id),
        }

    async def start(
        self,
        agent_id: str,
        command: str | None = None,
    ) -> dict[str, Any]:
        agent = self._runnable_agent(agent_id)
        selected_command = command or agent.run_command
        if not selected_command:
            raise ValueError(
                "Configure a run command before starting this agent"
            )
        if selected_command != agent.run_command:
            agent = agent.model_copy(
                update={"run_command": selected_command}
            )
            self.store.update_agent(agent)
            self.managed_workspace.sync(agent)

        current = self.process_manager.status(agent.id)
        already_running = current["status"] == "running"
        if already_running:
            process = current
        else:
            process = self.process_manager.start(
                agent.id,
                selected_command,
                self.workspace_access.validate_root(
                    Path(agent.workspace_root or "")
                ),
            )

        discovery: dict[str, Any] | None = None
        if agent.mcp_endpoint:
            try:
                discovery = await self._wait_for_discovery(agent.id)
            except Exception:
                if not already_running:
                    self.process_manager.stop(agent.id)
                raise
        return {
            **self.status(agent.id),
            "process": self.process_manager.status(agent.id),
            "already_running": already_running,
            "discovery": discovery,
        }

    def stop(self, agent_id: str) -> dict[str, Any]:
        self._agent(agent_id)
        current = self.process_manager.status(agent_id)
        if current["status"] != "running":
            process = current
        else:
            process = self.process_manager.stop(agent_id)
        return {
            **self.status(agent_id),
            "process": process,
        }

    async def discover(self, agent_id: str) -> dict[str, Any]:
        agent = self._agent(agent_id)
        architecture = self.store.architecture()
        discovered = await self.architecture_agent.discover_agent(
            agent,
            architecture,
        )
        self.store.update_agent(discovered)
        self.managed_workspace.sync(discovered)
        return {
            "agent_id": discovered.id,
            "endpoint": discovered.mcp_endpoint,
            "server_name": discovered.mcp_server_name,
            "tools": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "provider": tool.provider,
                }
                for tool in discovered.mcp_tools
            ],
            "enabled_tools": list(discovered.enabled_tools),
            "discovered_at": discovered.last_discovered_at,
            "status": discovered.status,
        }

    async def call_tool(
        self,
        agent_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        agent = self._agent(agent_id)
        capability = next(
            (
                tool
                for tool in agent.mcp_tools
                if tool.name == tool_name
            ),
            None,
        )
        if capability is None and agent.mcp_endpoint:
            await self.discover(agent.id)
            agent = self._agent(agent.id)
            capability = next(
                (
                    tool
                    for tool in agent.mcp_tools
                    if tool.name == tool_name
                ),
                None,
            )
        if capability is None:
            raise ValueError(
                f"{tool_name} is not a discovered tool for {agent.name}"
            )
        if agent.tool_policy == "disabled":
            raise ValueError(
                f"Tools are disabled for {agent.name}"
            )
        if (
            agent.enabled_tools
            and capability.name not in agent.enabled_tools
        ):
            raise ValueError(
                f"{tool_name} is not enabled for {agent.name}"
            )

        if capability.provider == "manager_runtime":
            if not capability.tool_id:
                raise ValueError(
                    f"{tool_name} is missing its registered tool link"
                )
            output = await self.registered_tool_executor(
                capability.tool_id,
                arguments,
            )
            endpoint = (
                f"local://registered-tools/{capability.tool_id}"
            )
        else:
            endpoint = (
                capability.provider_endpoint
                or agent.mcp_endpoint
                or ""
            )
            output = await self.mcp_client.call_tool(
                endpoint,
                capability.name,
                arguments,
            )
        return {
            "agent_id": agent.id,
            "tool_name": capability.name,
            "provider": capability.provider,
            "endpoint": endpoint,
            "arguments": arguments,
            "output": output,
        }

    async def _wait_for_discovery(
        self,
        agent_id: str,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for _ in range(40):
            process = self.process_manager.status(agent_id)
            if process["status"] == "failed":
                raise ValueError(
                    "Agent process exited before its MCP endpoint became ready"
                )
            try:
                return await self.discover(agent_id)
            except (httpx.HTTPError, ValueError, OSError) as exc:
                last_error = exc
                await asyncio.sleep(0.1)
        raise ValueError(
            "Agent process started, but its MCP endpoint did not become "
            f"ready: {last_error}"
        )

    def _agent(self, agent_id: str) -> AgentRecord:
        agent = next(
            (
                item
                for item in self.store.architecture().agents
                if item.id == agent_id
            ),
            None,
        )
        if agent is None:
            raise ValueError("Managed agent not found")
        return agent

    def _runnable_agent(self, agent_id: str) -> AgentRecord:
        agent = self._agent(agent_id)
        if not agent.imported or not agent.workspace_root:
            raise ValueError(
                "Only imported local agents have a runnable workspace"
            )
        return agent
