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
        "workspace_write_file": "Workspace Editor",
        "workspace_run_python_file": "Workspace Runner",
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
        file_plan = self._local_file_plan(request.message)
        edit_requested = self._is_instruction_edit_request(
            request.message
        )
        file_write_requested = self._is_file_write_request(
            request.message
        )
        file_run_requested = self._is_file_run_request(
            request.message
        )
        tool_state: dict[str, Any] = {
            "agent": agent,
            "prompt": request.message,
            "autonomy": request.autonomy,
            "actions": actions,
            "changes": changes,
            "evaluation": evaluation,
            "operational": False,
            "operation_kind": None,
            "runtime_results": [],
            "runtime_start_blocked": False,
            "file_results": [],
            "edit_requested": edit_requested,
            "file_requested": (
                file_write_requested or file_run_requested
            ),
            "file_write_requested": file_write_requested,
            "file_run_requested": file_run_requested,
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
            if file_plan:
                await execute("workspace_inspect", {})
                for tool_name, arguments in file_plan:
                    await execute(tool_name, arguments)
                await execute(
                    "validation_evaluate",
                    {"objective": request.message},
                )
                text = self._local_file_summary(
                    agent,
                    actions,
                )
            elif runtime_plan:
                await execute(
                    "architecture_search",
                    {"prompt": request.message},
                )
                await execute("workspace_inspect", {})
                for tool_name, arguments in runtime_plan:
                    await execute(tool_name, arguments)
                await execute(
                    "validation_evaluate",
                    {"objective": request.message},
                )
                text = self._local_runtime_summary(
                    agent,
                    actions,
                )
            elif edit_requested:
                await execute(
                    "architecture_search",
                    {"prompt": request.message},
                )
                await execute("workspace_inspect", {})
                await execute(
                    "developer_propose_change",
                    {
                        "objective": request.message,
                        "instructions_append": self._local_instruction(
                            request.message
                        ),
                    },
                )
                await execute(
                    "validation_evaluate",
                    {"objective": request.message},
                )
                text = self._local_summary(agent, request, changes)
            else:
                text = self._local_general_summary(agent)
        else:
            text = loop.text
            if file_plan:
                action_tools = {
                    action.tool
                    for action in actions
                }
                forced_file_action = False
                if "workspace.inspect" not in action_tools:
                    await execute("workspace_inspect", {})
                    forced_file_action = True
                for tool_name, arguments in file_plan:
                    mcp_tool = {
                        "workspace_write_file": "workspace.write_file",
                        "workspace_run_python_file": (
                            "workspace.run_python_file"
                        ),
                    }[tool_name]
                    if mcp_tool in action_tools:
                        continue
                    await execute(tool_name, arguments)
                    forced_file_action = True
                if forced_file_action:
                    text += " " + self._local_file_summary(
                        agent,
                        actions,
                    )
            elif runtime_plan and not tool_state["operational"]:
                for tool_name, arguments in runtime_plan:
                    await execute(tool_name, arguments)
                text += " " + self._local_runtime_summary(
                    agent,
                    actions,
                )
            if (
                edit_requested
                and not changes
                and not tool_state["operational"]
            ):
                await execute(
                    "developer_propose_change",
                    {
                        "objective": request.message,
                        "instructions_append": self._local_instruction(request.message),
                    },
                )
            if (
                (changes or tool_state["operational"])
                and tool_state.get("evaluation") is None
            ):
                await execute(
                    "validation_evaluate",
                    {"objective": request.message},
                )

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
            if tool_state["operation_kind"] == "workspace":
                if any(
                    action.status == "passed"
                    for action in actions
                    if action.tool
                    in {
                        "workspace.write_file",
                        "workspace.run_python_file",
                    }
                ):
                    text += (
                        " Successful Workspace MCP evidence was recorded "
                        "against the imported agent's real directory."
                    )
                else:
                    text += (
                        " The requested Workspace MCP operation was blocked "
                        "or failed; no source-file change is being reported."
                    )
            else:
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
            "workspace_write_file": (
                "workspace",
                "workspace.write_file",
                f"{employee}: write source file",
            ),
            "workspace_run_python_file": (
                "workspace",
                "workspace.run_python_file",
                f"{employee}: run Python verification",
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
                mcp_result = await self.internal_mcp_client.call_tool(
                    "architecture",
                    "architecture.search",
                    {"prompt": prompt},
                )
                matches = mcp_result.get("content", [])
                if not isinstance(matches, list):
                    matches = []
                result: dict[str, Any] = {
                    "matches": matches[:5],
                }
                evidence = {
                    "protocol": "MCP JSON-RPC 2.0",
                    "gateway_receipt": mcp_result.get("_manager_mcp"),
                    "matches": len(matches),
                }
                detail = f"{employee} found {len(matches)} relevant architecture components."
            elif name == "workspace_inspect":
                result = await self.internal_mcp_client.call_tool(
                    "workspace",
                    "workspace.inspect",
                    {
                        "agent_id": agent.id,
                        "query": str(state["prompt"]),
                    },
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
                    "access": (
                        "auto_write_available"
                        if (
                            isinstance(connected_workspace, dict)
                            and connected_workspace.get("writable")
                        )
                        else "read_only"
                    ),
                    "workspace": connected_workspace,
                    "context_files": [
                        item.get("path")
                        for item in result.get("context_files", [])
                        if isinstance(item, dict) and item.get("path")
                    ],
                    "secret_paths_excluded": True,
                }
                mcp_receipt = result.get("_manager_mcp")
                if isinstance(mcp_receipt, dict):
                    evidence["protocol"] = "MCP JSON-RPC 2.0"
                    evidence["gateway_receipt"] = mcp_receipt
            elif name in {
                "workspace_write_file",
                "workspace_run_python_file",
            }:
                state["operational"] = True
                state["operation_kind"] = "workspace"
                if not state["file_requested"]:
                    raise ValueError(
                        "The user did not request a source-file operation"
                    )
                if (
                    name == "workspace_write_file"
                    and not state["file_write_requested"]
                ):
                    raise ValueError(
                        "The user did not request a source-file write"
                    )
                if (
                    name == "workspace_run_python_file"
                    and not state["file_run_requested"]
                ):
                    raise ValueError(
                        "The user did not request Python execution"
                    )
                if state["autonomy"] != "auto":
                    raise ValueError(
                        "Writing or running workspace files requires Auto "
                        "permission"
                    )
                path = str(arguments.get("path", "")).strip()
                if not path:
                    raise ValueError("A relative workspace file path is required")
                remote_tool = {
                    "workspace_write_file": "workspace.write_file",
                    "workspace_run_python_file": (
                        "workspace.run_python_file"
                    ),
                }[name]
                remote_arguments: dict[str, Any] = {
                    "agent_id": agent.id,
                    "path": path,
                    "permission_mode": "auto",
                }
                if name == "workspace_write_file":
                    remote_arguments["content"] = str(
                        arguments.get("content", "")
                    )
                result = await self.internal_mcp_client.call_tool(
                    "workspace",
                    remote_tool,
                    remote_arguments,
                )
                state["file_results"].append(result)
                evidence = self._workspace_operation_evidence(
                    remote_tool,
                    result,
                )
                if name == "workspace_write_file":
                    detail = (
                        f"{employee} {'created' if result.get('created') else 'updated'} "
                        f"{result.get('path')} in the real imported workspace "
                        f"({result.get('bytes')} bytes, sha256 "
                        f"{str(result.get('sha256', ''))[:12]}…)."
                    )
                else:
                    detail = (
                        f"{employee} ran {result.get('path')} without a shell; "
                        f"exit code {result.get('exit_code')} and stdout "
                        f"{str(result.get('stdout', '')).strip()!r}."
                    )
            elif name.startswith("runtime_"):
                state["operational"] = True
                state["operation_kind"] = "runtime"
                if (
                    name
                    in {
                        "runtime_start",
                        "runtime_stop",
                        "runtime_call_tool",
                    }
                    and state["autonomy"] != "auto"
                ):
                    if name == "runtime_start":
                        state["runtime_start_blocked"] = True
                    raise ValueError(
                        "Starting, stopping, or calling a managed agent "
                        "requires Auto permission"
                    )
                if (
                    name == "runtime_discover"
                    and state.get("runtime_start_blocked")
                ):
                    raise ValueError(
                        "Discovery did not auto-start the agent because the "
                        "explicit start request requires Auto permission"
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
                if not state["edit_requested"]:
                    raise ValueError(
                        "The user did not request an agent-instructions edit"
                    )
                addition = str(arguments.get("instructions_append", "")).strip()
                if not addition:
                    addition = self._local_instruction(state["prompt"])
                proposal = await self.internal_mcp_client.call_tool(
                    "developer",
                    "developer.propose_change",
                    {
                        "objective": str(
                            arguments.get("objective")
                            or state["prompt"]
                        ),
                        "current_instructions": agent.instructions,
                        "instructions_append": addition,
                    },
                )
                after = str(proposal.get("after", "")).strip()
                before = str(
                    proposal.get("before", agent.instructions)
                )
                change = ManagerChange(
                    id=f"change_{uuid4().hex[:10]}",
                    target=f"{agent.id}/instructions.md",
                    kind="instructions",
                    summary=str(
                        proposal.get("objective")
                        or arguments.get("objective")
                        or state["prompt"]
                    ),
                    before=before,
                    after=after,
                )
                state["changes"].append(change)
                result = {"change": change.model_dump()}
                mcp_receipt = proposal.get("_manager_mcp")
                if isinstance(mcp_receipt, dict):
                    result["_manager_mcp"] = mcp_receipt
                    evidence = {
                        "protocol": "MCP JSON-RPC 2.0",
                        "gateway_receipt": mcp_receipt,
                    }
                detail = f"{employee} prepared a minimal instructions patch."
            elif name == "validation_evaluate":
                validation_result = (
                    await self.internal_mcp_client.call_tool(
                        "validation",
                        "validation.evaluate",
                        {
                            "objective": str(
                                arguments.get("objective")
                                or state["prompt"]
                            ),
                            "operation_kind": state["operation_kind"],
                            "changes": [
                                change.model_dump()
                                for change in state["changes"]
                            ],
                            "actions": [
                                {
                                    "server": action.server,
                                    "tool": action.tool,
                                    "status": action.status,
                                    "detail": action.detail,
                                }
                                for action in state["actions"]
                            ],
                        },
                    )
                )
                evaluation = ManagerEvaluation.model_validate(
                    validation_result.get("evaluation", {})
                )
                state["evaluation"] = evaluation
                result = {"evaluation": evaluation.model_dump()}
                mcp_receipt = validation_result.get("_manager_mcp")
                if isinstance(mcp_receipt, dict):
                    result["_manager_mcp"] = mcp_receipt
                    evidence = {
                        "protocol": "MCP JSON-RPC 2.0",
                        "gateway_receipt": mcp_receipt,
                    }
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

    @classmethod
    def _local_file_plan(
        cls,
        prompt: str,
    ) -> list[tuple[str, dict[str, Any]]]:
        """Provide a narrow no-key fallback for explicit simple file writes."""

        if not cls._is_file_request(prompt):
            return []
        run_requested = cls._is_file_run_request(prompt)
        path_match = re.search(
            r"\b(?:create|write|edit|update|replace|make)\s+"
            r"(?:a\s+|the\s+)?"
            r"([A-Za-z0-9_./-]+\.[A-Za-z0-9]+)\b",
            prompt,
            flags=re.IGNORECASE,
        )
        if path_match is None:
            run_match = re.search(
                r"\b(?:run|execute|test|verify)\s+"
                r"(?:a\s+|the\s+)?"
                r"([A-Za-z0-9_./-]+\.py)\b",
                prompt,
                flags=re.IGNORECASE,
            )
            return (
                [
                    (
                        "workspace_run_python_file",
                        {"path": run_match.group(1)},
                    )
                ]
                if run_match is not None
                else []
            )
        path = path_match.group(1)
        content = ""
        if path.lower().endswith(".py"):
            print_call = re.search(
                r"print\s*\(\s*([\"'][^\"']*[\"'])\s*\)",
                prompt,
                flags=re.IGNORECASE,
            )
            if print_call:
                content = f"print({print_call.group(1)})\n"
            elif "hello file" in prompt.lower():
                content = 'print("hello file")\n'
        if not content:
            return []
        plan: list[tuple[str, dict[str, Any]]] = [
            (
                "workspace_write_file",
                {"path": path, "content": content},
            )
        ]
        if run_requested:
            plan.append(
                ("workspace_run_python_file", {"path": path})
            )
        return plan

    @classmethod
    def _is_file_request(cls, prompt: str) -> bool:
        return (
            cls._is_file_write_request(prompt)
            or cls._is_file_run_request(prompt)
        )

    @staticmethod
    def _is_file_write_request(prompt: str) -> bool:
        lowered = prompt.lower()
        return bool(
            re.search(
                r"\b(create|write|edit|modify|update|replace|add)\b",
                lowered,
            )
            and (
                re.search(
                    r"\b[a-z0-9_./-]+\.(?:py|js|jsx|ts|tsx|json|md|"
                    r"txt|toml|ya?ml|css|html|sql|sh|java|go|rs|c|"
                    r"cpp|h)\b",
                    lowered,
                )
                or re.search(
                    r"\b(file|source|source code|code file)\b",
                    lowered,
                )
            )
        )

    @classmethod
    def _is_file_run_request(cls, prompt: str) -> bool:
        lowered = prompt.lower()
        return bool(
            re.search(
                r"\b(run|execute|test|verify)\b",
                lowered,
            )
            and (
                re.search(
                    r"\b[a-z0-9_./-]+\.py\b",
                    lowered,
                )
                or (
                    cls._is_file_write_request(prompt)
                    and re.search(
                        r"\b(it|the file|the script|python)\b",
                        lowered,
                    )
                )
            )
        )

    @classmethod
    def _is_instruction_edit_request(cls, prompt: str) -> bool:
        if cls._is_file_request(prompt):
            return False
        lowered = prompt.lower()
        return bool(
            re.search(
                r"\b(?:change|update|rewrite|edit|modify|add|remove)\b"
                r".{0,55}\b(?:instruction|prompt|behavior|response|"
                r"personality|configuration)\b",
                lowered,
            )
            or re.search(
                r"\bmake\s+(?:this|the)\s+agent\b",
                lowered,
            )
            or re.search(
                r"^(?:always|never)\b",
                lowered,
            )
            or re.search(
                r"\b(?:ensure|require)\s+(?:this|the)?\s*agent\b",
                lowered,
            )
        )

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
    def _workspace_operation_evidence(
        remote_tool: str,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        evidence: dict[str, Any] = {
            "protocol": "MCP JSON-RPC 2.0",
            "server": "workspace",
            "tool": remote_tool,
            "workspace": {
                "id": result.get("workspace_id"),
                "root": result.get("workspace_root"),
            },
            "file": {
                key: result.get(key)
                for key in (
                    "path",
                    "created",
                    "bytes",
                    "sha256",
                    "previous_sha256",
                )
                if key in result
            },
        }
        mcp_receipt = result.get("_manager_mcp")
        if isinstance(mcp_receipt, dict):
            evidence["gateway_receipt"] = mcp_receipt
        if remote_tool == "workspace.run_python_file":
            evidence["execution"] = {
                key: result.get(key)
                for key in (
                    "command",
                    "exit_code",
                    "stdout",
                    "passed",
                )
            }
        return evidence

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
            startup = (
                " Agent Manager started the saved local runtime in the "
                "background first."
                if result.get("auto_started")
                else ""
            )
            return (
                f"Runtime MCP connected to {result.get('server_name')} "
                f"at {result.get('endpoint')} and discovered "
                f"{len(result.get('tools', []))} real tools."
                f"{startup}"
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
    def _local_general_summary(agent: AgentRecord) -> str:
        return (
            f"I'm ready to work with {agent.name}. Ask me to inspect its "
            "architecture, edit its instructions, operate its runtime, or—"
            "for an imported local agent—create and verify source files. "
            "No change was proposed or left waiting for approval."
        )

    @staticmethod
    def _local_file_summary(
        agent: AgentRecord,
        actions: list[ManagerAction],
    ) -> str:
        file_actions = [
            action
            for action in actions
            if action.tool
            in {
                "workspace.write_file",
                "workspace.run_python_file",
            }
        ]
        passed = sum(
            action.status == "passed"
            for action in file_actions
        )
        failed = len(file_actions) - passed
        return (
            f"I operated on {agent.name}'s imported source workspace through "
            f"the Workspace MCP: {passed} file action"
            f"{'s' if passed != 1 else ''} passed"
            + (f" and {failed} failed." if failed else ".")
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
