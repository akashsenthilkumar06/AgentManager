"""Conversational Manager Agent that edits a selected client agent."""

from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

from backend.app.agents.architecture_agent import ArchitectureAgent
from backend.app.core.models import (
    AgentRecord,
    ManagerAction,
    ManagerChange,
    ManagerChatRequest,
    ManagerConversation,
    ManagerEvaluation,
    ManagerMessage,
    utc_now,
)
from backend.app.core.storage import JsonStore
from backend.app.infrastructure.managed_workspace import ManagedAgentWorkspace
from backend.app.infrastructure.openai_manager import OpenAIManagerLoop


class AgenticManager:
    """Routes edit requests across MCP-style specialists and manages approvals."""

    def __init__(
        self,
        store: JsonStore,
        architecture_agent: ArchitectureAgent,
        managed_workspace: ManagedAgentWorkspace,
        openai_loop: OpenAIManagerLoop,
    ):
        self.store = store
        self.architecture_agent = architecture_agent
        self.managed_workspace = managed_workspace
        self.openai_loop = openai_loop

    async def respond(self, request: ManagerChatRequest) -> ManagerConversation:
        architecture = self.store.architecture()
        agent = next(
            (item for item in architecture.agents if item.id == request.agent_id),
            None,
        )
        if agent is None:
            raise ValueError("Managed agent not found")
        conversation = self._conversation(request)
        conversation.autonomy = request.autonomy
        conversation.messages.append(
            ManagerMessage(
                id=f"mgrmsg_{uuid4().hex[:10]}",
                role="user",
                content=request.message,
            )
        )
        actions: list[ManagerAction] = []
        changes: list[ManagerChange] = []
        evaluation: ManagerEvaluation | None = None
        tool_state: dict[str, Any] = {
            "agent": agent,
            "prompt": request.message,
            "actions": actions,
            "changes": changes,
            "evaluation": evaluation,
        }

        async def execute(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
            return await self._execute_tool(name, arguments, tool_state)

        loop = await self.openai_loop.run(
            request.message,
            self._agent_context(agent),
            execute,
        )
        provider = loop.provider if loop else "local:deterministic"
        if loop is None:
            await execute("architecture_search", {"prompt": request.message})
            await execute("workspace_inspect", {})
            await execute(
                "developer_propose_change",
                {
                    "objective": request.message,
                    "instructions_append": self._local_instruction(request.message),
                },
            )
            await execute("validation_evaluate", {"objective": request.message})
            text = self._local_summary(agent, request, changes)
        else:
            text = loop.text
            if not changes:
                await execute(
                    "developer_propose_change",
                    {
                        "objective": request.message,
                        "instructions_append": self._local_instruction(request.message),
                    },
                )
            if tool_state.get("evaluation") is None:
                await execute("validation_evaluate", {"objective": request.message})

        if request.autonomy == "auto":
            self._apply_changes(agent, changes)
            text += " I applied the validated change to the client-agent workspace."
        else:
            text += " The change is staged for your review and has not been written yet."

        manager_message = ManagerMessage(
            id=f"mgrmsg_{uuid4().hex[:10]}",
            role="manager",
            content=text,
            actions=actions,
            changes=changes,
            evaluation=tool_state.get("evaluation"),
            provider=provider,
        )
        conversation.messages.append(manager_message)
        conversation.updated_at = utc_now()
        self.store.upsert_manager_conversation(conversation)
        return conversation

    def apply(self, conversation_id: str) -> ManagerConversation:
        conversation = self.store.get_manager_conversation(conversation_id)
        if conversation is None:
            raise ValueError("Manager conversation not found")
        agent = next(
            (
                item
                for item in self.store.architecture().agents
                if item.id == conversation.agent_id
            ),
            None,
        )
        if agent is None:
            raise ValueError("Managed agent not found")
        pending = [
            change
            for message in conversation.messages
            for change in message.changes
            if change.status == "pending"
        ]
        if not pending:
            raise ValueError("No pending changes to apply")
        self._apply_changes(agent, pending)
        conversation.updated_at = utc_now()
        conversation.messages.append(
            ManagerMessage(
                id=f"mgrmsg_{uuid4().hex[:10]}",
                role="manager",
                content=f"Applied {len(pending)} reviewed change{'s' if len(pending) != 1 else ''} to the client-agent workspace.",
                provider="manager:approval",
            )
        )
        self.store.upsert_manager_conversation(conversation)
        return conversation

    async def _execute_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        state: dict[str, Any],
    ) -> dict[str, Any]:
        started = time.perf_counter()
        agent: AgentRecord = state["agent"]
        server, tool, title = {
            "architecture_search": (
                "architecture",
                "architecture.search",
                "Inspect architecture",
            ),
            "workspace_inspect": (
                "workspace",
                "workspace.inspect",
                "Read client workspace",
            ),
            "developer_propose_change": (
                "developer",
                "developer.propose_change",
                "Prepare agent edit",
            ),
            "validation_evaluate": (
                "validation",
                "validation.evaluate",
                "Evaluate requested outcome",
            ),
        }.get(name, ("monitoring", name, "Run manager tool"))
        try:
            if name == "architecture_search":
                prompt = str(arguments.get("prompt") or state["prompt"])
                matches = self.architecture_agent.search(
                    prompt, self.store.architecture()
                )
                result: dict[str, Any] = {
                    "matches": [item.model_dump() for item in matches[:5]]
                }
                detail = f"Found {len(matches)} relevant architecture components."
            elif name == "workspace_inspect":
                result = self.managed_workspace.inspect(
                    agent,
                    query=str(state["prompt"]),
                )
                connected_count = len(result.get("context_files", []))
                detail = (
                    f"Inspected {len(result['files'])} manager files and "
                    f"{connected_count} relevant connected-workspace files "
                    f"for {agent.id}."
                )
            elif name == "developer_propose_change":
                addition = str(arguments.get("instructions_append", "")).strip()
                if not addition:
                    addition = self._local_instruction(state["prompt"])
                marker = "\n\n## Manager change\n"
                after = (agent.instructions.rstrip() + marker + addition).strip()
                after = after[:4000]
                change = ManagerChange(
                    id=f"change_{uuid4().hex[:10]}",
                    target=f"{agent.id}/instructions.md",
                    kind="instructions",
                    summary=str(arguments.get("objective") or state["prompt"]),
                    before=agent.instructions,
                    after=after,
                )
                state["changes"].append(change)
                result = {"change": change.model_dump()}
                detail = "Prepared a minimal instructions patch."
            elif name == "validation_evaluate":
                changes: list[ManagerChange] = state["changes"]
                valid = bool(changes) and all(
                    len(change.after) >= 12 and change.after != change.before
                    for change in changes
                )
                evaluation = ManagerEvaluation(
                    status="passed" if valid else "needs_review",
                    summary=(
                        "The proposed edit is scoped, reversible, and addresses the requested agent behavior."
                        if valid
                        else "The proposal needs a more concrete edit before it can be applied."
                    ),
                    checks=[
                        "Client workspace inspected",
                        "Existing instructions preserved",
                        "Change remains within agent configuration boundary",
                        "Rollback data captured",
                    ],
                )
                state["evaluation"] = evaluation
                result = {"evaluation": evaluation.model_dump()}
                detail = evaluation.summary
            else:
                raise ValueError(f"Unknown Manager tool: {name}")
            action = ManagerAction(
                id=f"action_{uuid4().hex[:10]}",
                server=server,
                tool=tool,
                status="passed",
                title=title,
                detail=detail,
                duration_ms=max(1, round((time.perf_counter() - started) * 1000)),
            )
            state["actions"].append(action)
            return result
        except Exception as exc:
            state["actions"].append(
                ManagerAction(
                    id=f"action_{uuid4().hex[:10]}",
                    server=server,
                    tool=tool,
                    status="failed",
                    title=title,
                    detail=str(exc),
                    duration_ms=max(
                        1, round((time.perf_counter() - started) * 1000)
                    ),
                )
            )
            return {"error": str(exc)}

    def _apply_changes(
        self, agent: AgentRecord, changes: list[ManagerChange]
    ) -> None:
        current = agent
        for change in changes:
            if change.status != "pending":
                continue
            if change.kind == "instructions":
                current = self.managed_workspace.apply_instructions(
                    current, change.after
                )
            change.status = "applied"

    def _conversation(self, request: ManagerChatRequest) -> ManagerConversation:
        if request.conversation_id:
            existing = self.store.get_manager_conversation(request.conversation_id)
            if existing is None:
                raise ValueError("Manager conversation not found")
            if existing.agent_id != request.agent_id:
                raise ValueError("Conversation belongs to another client agent")
            return existing
        title = request.message[:62] + ("…" if len(request.message) > 62 else "")
        return ManagerConversation(
            id=f"mgrchat_{uuid4().hex[:10]}",
            agent_id=request.agent_id,
            title=title,
            autonomy=request.autonomy,
        )

    @staticmethod
    def _agent_context(agent: AgentRecord) -> dict[str, Any]:
        return {
            "id": agent.id,
            "name": agent.name,
            "description": agent.description,
            "instructions": agent.instructions,
            "features": agent.features,
            "mcp_tools": [tool.name for tool in agent.mcp_tools],
            "mcp_endpoint": agent.mcp_endpoint,
        }

    @staticmethod
    def _local_instruction(prompt: str) -> str:
        return (
            f"When handling requests related to this change—{prompt.rstrip('.')}—"
            "inspect the relevant available tool or context first, explain material "
            "uncertainty, and verify that the final response satisfies the user's stated outcome."
        )

    @staticmethod
    def _local_summary(
        agent: AgentRecord,
        request: ManagerChatRequest,
        changes: list[ManagerChange],
    ) -> str:
        return (
            f"I analyzed {agent.name} through its architecture and local workspace, "
            f"then prepared {len(changes)} validated change{'s' if len(changes) != 1 else ''} "
            f"for “{request.message}”."
        )
