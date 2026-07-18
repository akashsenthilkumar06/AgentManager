"""Conversational Manager Agent that edits a selected client agent."""

from __future__ import annotations

import re
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
from backend.app.infrastructure.internal_mcp_client import InternalMCPClient
from backend.app.infrastructure.managed_workspace import ManagedAgentWorkspace
from backend.app.infrastructure.openai_manager import OpenAIManagerLoop


class AgenticManager:
    """Edits and operates selected agents with reviewable evidence."""

    _EMPLOYEE_BY_TOOL: dict[str, str] = {
        "architecture_search": "Architecture Analyst",
        "workspace_inspect": "Workspace Inspector",
        "developer_propose_change": "Developer Specialist",
        "validation_evaluate": "Validation Specialist",
        "runtime_status": "Runtime Operator",
        "runtime_start": "Runtime Operator",
        "runtime_stop": "Runtime Operator",
        "runtime_discover": "Runtime Operator",
        "runtime_call_tool": "Runtime Operator",
    }

    def __init__(
        self,
        store: JsonStore,
        architecture_agent: ArchitectureAgent,
        managed_workspace: ManagedAgentWorkspace,
        openai_loop: OpenAIManagerLoop,
        internal_mcp_client: InternalMCPClient,
    ):
        self.store = store
        self.architecture_agent = architecture_agent
        self.managed_workspace = managed_workspace
        self.openai_loop = openai_loop
        self.internal_mcp_client = internal_mcp_client

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
        runtime_plan = self._local_runtime_plan(
            agent,
            request.message,
        )
        tool_state: dict[str, Any] = {
            "agent": agent,
            "prompt": request.message,
            "autonomy": request.autonomy,
            "actions": actions,
            "changes": changes,
            "evaluation": evaluation,
            "operational": False,
            "runtime_results": [],
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
            if runtime_plan:
                for tool_name, arguments in runtime_plan:
                    await execute(tool_name, arguments)
            else:
                await execute(
                    "developer_propose_change",
                    {
                        "objective": request.message,
                        "instructions_append": self._local_instruction(
                            request.message
                        ),
                    },
                )
            await execute("validation_evaluate", {"objective": request.message})
            text = (
                self._local_runtime_summary(
                    agent,
                    actions,
                )
                if runtime_plan
                else self._local_summary(agent, request, changes)
            )
        else:
            text = loop.text
            if runtime_plan and not tool_state["operational"]:
                for tool_name, arguments in runtime_plan:
                    await execute(tool_name, arguments)
                text += " " + self._local_runtime_summary(
                    agent,
                    actions,
                )
            if not changes and not tool_state["operational"]:
                await execute(
                    "developer_propose_change",
                    {
                        "objective": request.message,
                        "instructions_append": self._local_instruction(request.message),
                    },
                )
            if tool_state.get("evaluation") is None:
                await execute("validation_evaluate", {"objective": request.message})

        if changes:
            if request.autonomy == "auto":
                self._apply_changes(agent, changes)
                text += (
                    " I applied the validated change to the "
                    "client-agent workspace."
                )
            else:
                text += (
                    " The change is staged for your review and has "
                    "not been written yet."
                )
        elif tool_state["operational"]:
            text += (
                " Runtime evidence was recorded without changing the "
                "agent's files or instructions."
            )

        text += self._delegation_summary(actions)

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
        conversation.messages.append(
            ManagerMessage(
                id=f"mgrmsg_{uuid4().hex[:10]}",
                role="manager",
                content=f"Applied {len(pending)} reviewed change{'s' if len(pending) != 1 else ''} to the client-agent workspace.",
                provider="manager:approval",
            )
        )
        conversation.updated_at = utc_now()
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
        employee = self._EMPLOYEE_BY_TOOL.get(name, "Operations Specialist")
        server, tool, title = {
            "architecture_search": (
                "architecture",
                "architecture.search",
                f"{employee}: inspect architecture",
            ),
            "workspace_inspect": (
                "workspace",
                "workspace.inspect",
                f"{employee}: inspect client workspace",
            ),
            "developer_propose_change": (
                "developer",
                "developer.propose_change",
                f"{employee}: prepare agent edit",
            ),
            "validation_evaluate": (
                "validation",
                "validation.evaluate",
                f"{employee}: evaluate requested outcome",
            ),
            "runtime_status": (
                "runtime",
                "runtime.status",
                f"{employee}: inspect agent runtime",
            ),
            "runtime_start": (
                "runtime",
                "runtime.start",
                f"{employee}: launch independent agent",
            ),
            "runtime_stop": (
                "runtime",
                "runtime.stop",
                f"{employee}: stop independent agent",
            ),
            "runtime_discover": (
                "runtime",
                "runtime.discover",
                f"{employee}: discover live capabilities",
            ),
            "runtime_call_tool": (
                "runtime",
                "runtime.call_tool",
                f"{employee}: call managed-agent tool",
            ),
        }.get(name, ("monitoring", name, f"{employee}: run manager tool"))
        evidence: dict[str, Any] = {}
        try:
            if name == "architecture_search":
                prompt = str(arguments.get("prompt") or state["prompt"])
                matches = self.architecture_agent.search(
                    prompt, self.store.architecture()
                )
                result: dict[str, Any] = {
                    "matches": [item.model_dump() for item in matches[:5]]
                }
                detail = f"{employee} found {len(matches)} relevant architecture components."
            elif name == "workspace_inspect":
                result = self.managed_workspace.inspect(
                    agent,
                    query=str(state["prompt"]),
                )
                connected_count = len(result.get("context_files", []))
                detail = (
                    f"{employee} inspected {len(result['files'])} manager files and "
                    f"{connected_count} relevant connected-workspace files "
                    f"for {agent.id}."
                )
                connected_workspace = result.get(
                    "connected_workspace"
                )
                evidence = {
                    "access": "read_only",
                    "workspace": connected_workspace,
                    "context_files": [
                        item.get("path")
                        for item in result.get("context_files", [])
                        if isinstance(item, dict) and item.get("path")
                    ],
                    "secret_paths_excluded": True,
                }
            elif name.startswith("runtime_"):
                state["operational"] = True
                if (
                    name
                    in {
                        "runtime_start",
                        "runtime_stop",
                        "runtime_call_tool",
                    }
                    and state["autonomy"] != "auto"
                ):
                    raise ValueError(
                        "Starting, stopping, or calling a managed agent "
                        "requires Auto permission"
                    )
                remote_tool = {
                    "runtime_status": "runtime.status",
                    "runtime_start": "runtime.start",
                    "runtime_stop": "runtime.stop",
                    "runtime_discover": "runtime.discover",
                    "runtime_call_tool": "runtime.call_tool",
                }[name]
                remote_arguments: dict[str, Any] = {
                    "agent_id": agent.id,
                }
                if name == "runtime_call_tool":
                    tool_name = str(
                        arguments.get("tool_name", "")
                    ).strip()
                    tool_arguments = arguments.get("arguments", {})
                    if not tool_name:
                        raise ValueError(
                            "A discovered tool name is required"
                        )
                    if not isinstance(tool_arguments, dict):
                        raise ValueError(
                            "Managed-agent tool arguments must be an object"
                        )
                    remote_arguments.update(
                        {
                            "tool_name": tool_name,
                            "arguments": tool_arguments,
                        }
                    )
                result = await self.internal_mcp_client.call_tool(
                    "runtime",
                    remote_tool,
                    remote_arguments,
                )
                state["runtime_results"].append(result)
                evidence = self._runtime_evidence(
                    remote_tool,
                    result,
                )
                detail = self._runtime_detail(
                    agent,
                    remote_tool,
                    result,
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
                detail = f"{employee} prepared a minimal instructions patch."
            elif name == "validation_evaluate":
                changes: list[ManagerChange] = state["changes"]
                valid_change = bool(changes) and all(
                    len(change.after) >= 12 and change.after != change.before
                    for change in changes
                )
                runtime_actions = [
                    action
                    for action in state["actions"]
                    if action.server == "runtime"
                ]
                valid_runtime = (
                    bool(runtime_actions)
                    and all(
                        action.status == "passed"
                        for action in runtime_actions
                    )
                )
                valid = valid_change or valid_runtime
                if state["operational"]:
                    summary = (
                        "The Manager reached the selected agent through "
                        "the Runtime MCP and recorded real process, "
                        "discovery, or tool-call evidence."
                        if valid_runtime
                        else "One or more requested runtime operations failed; "
                        "review the action evidence before relying on the agent."
                    )
                    checks = [
                        "Scoped workspace access confirmed",
                        "Runtime operation used the Agent Runtime MCP",
                        "Process and endpoint state captured",
                        "Live tool provenance retained when a tool was called",
                    ]
                else:
                    summary = (
                        "The proposed edit is scoped, reversible, and "
                        "addresses the requested agent behavior."
                        if valid
                        else "The proposal needs a more concrete edit "
                        "before it can be applied."
                    )
                    checks = [
                        "Client workspace inspected",
                        "Existing instructions preserved",
                        "Change remains within agent configuration boundary",
                        "Rollback data captured",
                    ]
                evaluation = ManagerEvaluation(
                    status="passed" if valid else "needs_review",
                    summary=summary,
                    checks=checks,
                )
                state["evaluation"] = evaluation
                result = {"evaluation": evaluation.model_dump()}
                detail = f"{employee}: {evaluation.summary}"
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
                evidence=evidence,
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

    @classmethod
    def _local_runtime_plan(
        cls,
        agent: AgentRecord,
        prompt: str,
    ) -> list[tuple[str, dict[str, Any]]]:
        lowered = prompt.lower()
        stop_requested = bool(
            re.search(
                r"\b(stop|shutdown|shut down|terminate|kill)\b",
                lowered,
            )
        )
        start_requested = bool(
            re.search(
                r"\b(start|run|launch|boot|bring online|ensure live)\b",
                lowered,
            )
        )
        discover_requested = bool(
            re.search(
                r"\b(discover|sync|refresh|capabilities|available tools|"
                r"advertised tools|access)\b",
                lowered,
            )
        )
        status_requested = bool(
            re.search(
                r"\b(runtime|process|running|status|logs|reachable|"
                r"accessible)\b",
                lowered,
            )
        )
        call_requested = bool(
            re.search(
                r"\b(call|invoke|execute)\b",
                lowered,
            )
        )
        if not any(
            (
                stop_requested,
                start_requested,
                discover_requested,
                status_requested,
                call_requested,
            )
        ):
            return []

        plan: list[tuple[str, dict[str, Any]]] = [
            ("runtime_status", {})
        ]
        if stop_requested:
            plan.append(("runtime_stop", {}))
            return plan
        if start_requested:
            plan.append(("runtime_start", {}))
        if discover_requested or start_requested or call_requested:
            plan.append(("runtime_discover", {}))
        if call_requested:
            tool_name = cls._infer_tool_name(agent, prompt)
            if tool_name:
                arguments = cls._infer_tool_arguments(
                    agent,
                    tool_name,
                    prompt,
                )
                if arguments is not None:
                    plan.append(
                        (
                            "runtime_call_tool",
                            {
                                "tool_name": tool_name,
                                "arguments": arguments,
                            },
                        )
                    )
        return plan

    @staticmethod
    def _infer_tool_name(
        agent: AgentRecord,
        prompt: str,
    ) -> str | None:
        lowered = prompt.lower()
        for capability in agent.mcp_tools:
            if capability.name.lower() in lowered:
                return capability.name
        match = re.search(
            r"\b(?:call|invoke|execute)\s+(?:the\s+)?"
            r"(?:tool\s+)?([a-zA-Z_][a-zA-Z0-9_.-]+)",
            prompt,
        )
        if match and match.group(1).lower() not in {
            "agent",
            "it",
            "this",
            "tool",
        }:
            return match.group(1)
        enabled = [
            capability.name
            for capability in agent.mcp_tools
            if (
                not agent.enabled_tools
                or capability.name in agent.enabled_tools
            )
        ]
        return enabled[0] if len(enabled) == 1 else None

    @staticmethod
    def _infer_tool_arguments(
        agent: AgentRecord,
        tool_name: str,
        prompt: str,
    ) -> dict[str, Any] | None:
        capability = next(
            (
                tool
                for tool in agent.mcp_tools
                if tool.name == tool_name
            ),
            None,
        )
        required = (
            capability.input_schema.get("required", [])
            if capability
            else []
        )
        required = [
            str(name)
            for name in required
            if isinstance(name, str)
        ]
        arguments: dict[str, Any] = {}
        patterns = {
            "ticket_id": r"\bTCK-\d+\b",
            "order_id": r"\bORD-\d+\b",
            "sku": r"\bSKU-[A-Z0-9-]+\b",
        }
        upper_prompt = prompt.upper()
        for name, pattern in patterns.items():
            match = re.search(pattern, upper_prompt)
            if match and (not required or name in required):
                arguments[name] = match.group(0)
        for name in required:
            if name in arguments:
                continue
            match = re.search(
                rf"\b{re.escape(name)}\s*(?:=|:)\s*"
                r"[\"']?([^,\s\"']+)",
                prompt,
                flags=re.IGNORECASE,
            )
            if match:
                arguments[name] = match.group(1)
        if required and any(
            name not in arguments for name in required
        ):
            return None
        if not required and not arguments:
            ticket = re.search(r"\bTCK-\d+\b", upper_prompt)
            if ticket and "ticket" in tool_name.lower():
                arguments["ticket_id"] = ticket.group(0)
        return arguments

    @staticmethod
    def _runtime_evidence(
        remote_tool: str,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        evidence: dict[str, Any] = {
            "protocol": "MCP JSON-RPC 2.0",
            "server": "runtime",
            "tool": remote_tool,
        }
        mcp_receipt = result.get("_manager_mcp")
        if isinstance(mcp_receipt, dict):
            evidence["gateway_receipt"] = mcp_receipt
        process = result.get("process")
        if isinstance(process, dict):
            evidence["process"] = {
                key: process.get(key)
                for key in (
                    "status",
                    "pid",
                    "command",
                    "started_at",
                    "exit_code",
                )
            }
        workspace = result.get("workspace")
        if isinstance(workspace, dict):
            evidence["workspace"] = workspace
        discovery = result.get("discovery")
        if isinstance(discovery, dict):
            evidence["discovery"] = discovery
        if remote_tool == "runtime.discover":
            evidence["discovery"] = result
        if remote_tool == "runtime.call_tool":
            evidence["tool_call"] = result
        return evidence

    @staticmethod
    def _runtime_detail(
        agent: AgentRecord,
        remote_tool: str,
        result: dict[str, Any],
    ) -> str:
        process = result.get("process", {})
        if not isinstance(process, dict):
            process = {}
        if remote_tool == "runtime.status":
            workspace = result.get("workspace") or {}
            return (
                f"Runtime MCP inspected {agent.name}: process "
                f"{process.get('status', 'unknown')}, endpoint "
                f"{result.get('endpoint') or 'not configured'}, and "
                f"{workspace.get('files', 0)} accessible source files."
            )
        if remote_tool == "runtime.start":
            discovery = result.get("discovery") or {}
            return (
                f"Runtime MCP launched {agent.name} as PID "
                f"{process.get('pid')} with its saved command; endpoint "
                f"{discovery.get('endpoint') or result.get('endpoint')} "
                f"advertised {len(discovery.get('tools', []))} tools."
            )
        if remote_tool == "runtime.stop":
            return (
                f"Runtime MCP stopped {agent.name}; process status is "
                f"{process.get('status', 'unknown')} and PID is "
                f"{process.get('pid')}."
            )
        if remote_tool == "runtime.discover":
            return (
                f"Runtime MCP connected to {result.get('server_name')} "
                f"at {result.get('endpoint')} and discovered "
                f"{len(result.get('tools', []))} real tools."
            )
        output = result.get("output", {})
        if not isinstance(output, dict):
            output = {"content": output}
        source = output.get("source")
        proof = output.get("proof")
        provenance = ", ".join(
            item
            for item in (
                f"source={source}" if source else "",
                f"proof={proof}" if proof else "",
            )
            if item
        )
        return (
            f"Runtime MCP called {result.get('tool_name')} through "
            f"{result.get('provider')} at {result.get('endpoint')}"
            + (f"; {provenance}." if provenance else ".")
        )

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
            "imported": agent.imported,
            "workspace_root": agent.workspace_root,
            "run_command": agent.run_command,
            "detected_entrypoints": agent.detected_entrypoints,
            "openai_model": agent.openai_model,
            "openai_reasoning_effort": agent.openai_reasoning_effort,
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

    @staticmethod
    def _local_runtime_summary(
        agent: AgentRecord,
        actions: list[ManagerAction],
    ) -> str:
        runtime_actions = [
            action
            for action in actions
            if action.server == "runtime"
        ]
        passed = sum(
            action.status == "passed"
            for action in runtime_actions
        )
        failed = len(runtime_actions) - passed
        return (
            f"I operated {agent.name} through the Agent Runtime MCP: "
            f"{passed} runtime action{'s' if passed != 1 else ''} passed"
            + (
                f" and {failed} failed."
                if failed
                else "."
            )
        )

    def _delegation_summary(self, actions: list[ManagerAction]) -> str:
        if not actions:
            return ""
        entries = [
            f"{index + 1}) {action.title}"
            for index, action in enumerate(actions)
            if action.status == "passed"
        ]
        if not entries:
            return ""
        return "\n\nDelegation trace:\n" + "\n".join(entries)
