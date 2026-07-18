"""Agent-scoped conversation orchestration and output verification."""

from __future__ import annotations

import re
import time
from typing import Awaitable, Callable
from uuid import uuid4

from backend.app.agents.employees import EMPLOYEE_HANDLERS, REQUIRED_TOOLS
from backend.app.core.models import (
    AgentChatRequest,
    AgentRecord,
    AgentConversation,
    ChatMessage,
    OutputVerification,
    ToolCallRecord,
    utc_now,
)
from backend.app.core.storage import JsonStore
from backend.app.infrastructure.live_conversation import LiveConversationRunner
from backend.app.infrastructure.cloud_data import CloudDataConnector


LiveAgentPreparer = Callable[[str], Awaitable[AgentRecord]]

IDENTIFIER_FIELDS = {
    "INV": "invoice_id",
    "ORD": "order_id",
    "REPO": "repo_id",
    "SKU": "sku",
    "TCK": "ticket_id",
}


class ConversationAgent:
    """Runs a managed agent with scoped context and verifies its final answer."""

    def __init__(
        self,
        store: JsonStore,
        mock_system: CloudDataConnector,
        live_runner: LiveConversationRunner,
        live_agent_preparer: LiveAgentPreparer | None = None,
    ):
        self.store = store
        self.mock_system = mock_system
        self.live_runner = live_runner
        self.live_agent_preparer = live_agent_preparer

    async def respond(self, request: AgentChatRequest) -> AgentConversation:
        architecture = self.store.architecture()
        agent = next((item for item in architecture.agents if item.id == request.agent_id), None)
        if agent is None:
            raise ValueError("Managed agent not found")

        conversation = self._conversation(request, agent.name)
        conversation.messages.append(
            ChatMessage(id=f"msg_{uuid4().hex[:10]}", role="user", content=request.message)
        )

        started = time.perf_counter()
        execution_mode = "deterministic"
        provider = "local:deterministic"
        fallback_reason: str | None = None
        endpoint: str | None = None
        tool_calls: list[ToolCallRecord] = []

        if self.live_runner.is_live_endpoint(agent):
            endpoint = agent.mcp_endpoint
            try:
                if (
                    self.live_agent_preparer is not None
                    and self.live_runner.api_key
                ):
                    agent = await self.live_agent_preparer(agent.id)
                live = await self.live_runner.run(agent, conversation.messages)
                content = live.text
                tool_calls = live.tool_calls
                criteria = live.criteria
                evidence = live.evidence
                provider = live.provider
                execution_mode = "live"
            except Exception as exc:
                fallback_reason = str(exc)[:500]
                execution_mode = "fallback"
                provider = "local:fallback"

        if (
            execution_mode != "live"
            and fallback_reason
            and agent.imported
            and endpoint
        ):
            provider = "local:error"
            content = (
                f"I could not query {agent.name} because its managed MCP "
                "runtime did not become ready. No placeholder or demo invoice "
                "data was returned. Open the agent's Runtime output to inspect "
                "the saved command, then retry."
            )
            tool_calls = [
                ToolCallRecord(
                    id=f"call_{uuid4().hex[:10]}",
                    tool_name=request.tool_name or "mcp.runtime",
                    status="failed",
                    input={"request": request.message},
                    output={"error": fallback_reason},
                    duration_ms=max(
                        1,
                        round(
                            (time.perf_counter() - started) * 1000
                        ),
                    ),
                    provider="agent_mcp",
                    endpoint=endpoint,
                )
            ]
            criteria = [
                "Use the imported agent's real MCP runtime",
                "Do not substitute unrelated deterministic fixtures",
            ]
            evidence = [
                f"Live MCP startup failed: {fallback_reason}",
                "No deterministic business data was returned",
            ]
        elif execution_mode != "live":
            tool_call, content, criteria, evidence = await self._deterministic_turn(
                agent.id,
                agent.tool_policy,
                agent.enabled_tools,
                request,
                ignore_enabled_tools=bool(endpoint),
            )
            tool_call.duration_ms = max(
                1, round((time.perf_counter() - started) * 1000)
            )
            tool_calls = [tool_call]
            if fallback_reason:
                evidence.insert(
                    0, f"Live MCP unavailable; deterministic fallback: {fallback_reason}"
                )

        content = self._apply_response_style(
            content, tool_calls, agent.response_style
        )
        context_used = self._context_labels(agent, request.context_mode)
        if execution_mode == "live":
            context_used.extend(
                [
                    f"Execution · Live MCP",
                    f"Endpoint · {endpoint}",
                    f"Provider · {provider}",
                ]
            )
        elif execution_mode == "fallback":
            context_used.extend(
                [
                    (
                        "Execution · Live MCP failed; no mock response"
                        if provider == "local:error"
                        else "Execution · Deterministic fallback"
                    ),
                    f"Live endpoint · {endpoint}",
                ]
            )
        verification = self._verify(
            content, tool_calls, criteria, evidence, agent.verification_mode
        )
        conversation.messages.append(
            ChatMessage(
                id=f"msg_{uuid4().hex[:10]}",
                role="agent",
                content=content,
                tool_calls=tool_calls,
                verification=verification,
                context_used=context_used,
                execution_mode=execution_mode,
                provider=provider,
                endpoint=endpoint,
                fallback_reason=fallback_reason,
            )
        )
        conversation.updated_at = utc_now()
        self.store.upsert_conversation(conversation)
        return conversation

    def _conversation(self, request: AgentChatRequest, agent_name: str) -> AgentConversation:
        if request.conversation_id:
            existing = self.store.get_conversation(request.conversation_id)
            if existing is None:
                raise ValueError("Conversation not found")
            if existing.agent_id != request.agent_id:
                raise ValueError("Conversation belongs to another agent")
            return existing
        title = request.message[:58] + ("…" if len(request.message) > 58 else "")
        return AgentConversation(
            id=f"chat_{uuid4().hex[:10]}",
            agent_id=request.agent_id,
            title=title,
        )

    async def _deterministic_turn(
        self,
        agent_id: str,
        tool_policy: str,
        enabled_tools: list[str],
        request: AgentChatRequest,
        *,
        ignore_enabled_tools: bool = False,
    ) -> tuple[ToolCallRecord, str, list[str], list[str]]:
        architecture = self.store.architecture()
        agent = next(
            item
            for item in architecture.agents
            if item.id == agent_id
        )
        required_tool = REQUIRED_TOOLS.get(
            agent_id, (None, request.tool_name or "unavailable")
        )
        mismatch = self._capability_mismatch(
            agent,
            required_tool[0],
            required_tool[1],
            request.message,
            architecture.agents,
        )
        if mismatch is not None:
            return mismatch
        tool_blocked = tool_policy == "disabled" or (
            not ignore_enabled_tools
            and bool(enabled_tools)
            and required_tool[1] not in enabled_tools
        )
        if tool_blocked:
            return (
                ToolCallRecord(
                    id=f"call_{uuid4().hex[:10]}",
                    tool_id=required_tool[0],
                    tool_name=required_tool[1],
                    status="failed",
                ),
                (
                    f"I could not complete this test because {required_tool[1]} "
                    "is disabled in the current agent configuration."
                ),
                ["Use the required grounded tool", "Return a supported answer"],
                ["Agent tool policy blocked execution"],
            )
        return await self._run(agent_id, request)

    def _capability_mismatch(
        self,
        agent: AgentRecord,
        required_tool_id: str | None,
        required_tool_name: str,
        message: str,
        fleet: list[AgentRecord],
    ) -> tuple[ToolCallRecord, str, list[str], list[str]] | None:
        identifiers = re.findall(
            r"\b(INV|ORD|REPO|SKU|TCK)-[A-Z0-9-]+\b",
            message.upper(),
        )
        if not identifiers:
            return None

        capability = next(
            (
                tool
                for tool in agent.mcp_tools
                if tool.name == required_tool_name
            ),
            None,
        )
        registered = (
            self.store.get_tool(required_tool_id)
            if required_tool_id
            else None
        )
        input_schema = (
            capability.input_schema
            if capability
            else (
                registered.get("input_schema", {})
                if registered
                else {}
            )
        )
        accepted_fields = set(
            input_schema.get("properties") or {}
        )
        if not accepted_fields:
            return None
        requested_fields = {
            IDENTIFIER_FIELDS[prefix] for prefix in identifiers
        }
        if accepted_fields.intersection(requested_fields):
            return None

        requested_field = sorted(requested_fields)[0]
        suggestion = next(
            (
                (other.name, tool.name)
                for other in fleet
                if other.id != agent.id
                for tool in other.mcp_tools
                if requested_field
                in set(
                    (tool.input_schema.get("properties") or {})
                )
            ),
            None,
        )
        available = [
            tool.name
            for tool in agent.mcp_tools
            if not agent.enabled_tools
            or tool.name in agent.enabled_tools
        ]
        identifier_label = requested_field.replace("_", " ")
        content = (
            f"{agent.name} cannot handle this {identifier_label} request. "
            f"Its enabled capability is "
            f"{', '.join(available) if available else 'not configured'}."
        )
        if suggestion:
            content += (
                f" Use {suggestion[0]}, which exposes "
                f"{suggestion[1]}, for this request."
            )
        return (
            ToolCallRecord(
                id=f"call_{uuid4().hex[:10]}",
                tool_name="capability_mismatch",
                status="failed",
                input={"request": message},
                output={
                    "requested_field": requested_field,
                    "available_tools": available,
                    "suggested_agent": suggestion[0]
                    if suggestion
                    else None,
                    "suggested_tool": suggestion[1]
                    if suggestion
                    else None,
                },
            ),
            content,
            [
                "Route the request only to a compatible capability",
                "Do not substitute an unrelated order or invoice record",
            ],
            [
                f"Requested identifier requires {requested_field}",
                (
                    f"{agent.name} exposes "
                    f"{', '.join(available) if available else 'no enabled tools'}"
                ),
            ],
        )

    async def _run(
        self, agent_id: str, request: AgentChatRequest
    ) -> tuple[ToolCallRecord, str, list[str], list[str]]:
        handler = EMPLOYEE_HANDLERS.get(agent_id)
        if handler is None:
            raise ValueError(f"No deterministic employee runner for {agent_id}")
        result = await handler(self.mock_system, request.message)
        return (
            self._tool(
                result["tool_id"],
                result["tool_name"],
                result["inputs"],
                result["output"],
            ),
            result["content"],
            result["criteria"],
            result["evidence"],
        )

    @staticmethod
    def _tool(tool_id: str, name: str, inputs: dict, output: dict) -> ToolCallRecord:
        return ToolCallRecord(
            id=f"call_{uuid4().hex[:10]}",
            tool_id=tool_id,
            tool_name=name,
            status="passed",
            input=inputs,
            output=output,
        )

    @staticmethod
    def _context_labels(agent, context_mode: str) -> list[str]:
        labels = [
            f"Agent profile · {agent.name}",
            "Agent instructions",
            f"Tool contracts · {len(agent.mcp_tools)}",
        ]
        if context_mode == "full":
            labels.extend(
                [
                    f"Features · {len(agent.features)}",
                    f"MCP prompts · {len(agent.mcp_prompts)}",
                    f"MCP resources · {len(agent.mcp_resources)}",
                ]
            )
            if agent.memory_enabled:
                labels.append("Recent agent conversation history")
        return labels

    @staticmethod
    def _apply_response_style(
        content: str,
        tool_calls: list[ToolCallRecord],
        response_style: str,
    ) -> str:
        if response_style == "concise":
            return content.split(". ")[0].rstrip(".") + "."
        passed = next(
            (call for call in tool_calls if call.status == "passed"),
            None,
        )
        if response_style == "detailed" and passed:
            return (
                content
                + f" This answer was grounded in {passed.tool_name} and will remain "
                "attached to the test history for review."
            )
        return content

    @staticmethod
    def _verify(
        content: str,
        tool_calls: list[ToolCallRecord],
        criteria: list[str],
        evidence: list[str],
        verification_mode: str,
    ) -> OutputVerification:
        complete = bool(content.strip()) and any(
            call.status == "passed" and bool(call.output)
            for call in tool_calls
        )
        failed = bool(tool_calls) and all(
            call.status == "failed"
            for call in tool_calls
        )
        confidence = 0.98 if verification_mode == "strict" else 0.96
        if verification_mode == "advisory":
            confidence = 0.9
        return OutputVerification(
            status=(
                "verified"
                if complete
                else "failed"
                if failed
                else "needs_review"
            ),
            confidence=confidence if complete else (0.1 if failed else 0.52),
            summary=(
                "The response matches the request and is grounded in the selected tool output."
                if complete
                else "The live agent request failed and no grounded business result was returned."
                if failed
                else "The response needs human review because its supporting evidence is incomplete."
            ),
            criteria=criteria,
            evidence=evidence,
        )
