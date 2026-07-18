"""Agent-scoped conversation orchestration and output verification."""

from __future__ import annotations

import time
from uuid import uuid4

from backend.app.agents.employees import EMPLOYEE_HANDLERS, REQUIRED_TOOLS
from backend.app.core.models import (
    AgentChatRequest,
    AgentConversation,
    ChatMessage,
    OutputVerification,
    ToolCallRecord,
    utc_now,
)
from backend.app.core.storage import JsonStore
from backend.app.infrastructure.live_conversation import LiveConversationRunner
from backend.app.infrastructure.cloud_data import CloudDataConnector


class ConversationAgent:
    """Runs a managed agent with scoped context and verifies its final answer."""

    def __init__(
        self,
        store: JsonStore,
        mock_system: CloudDataConnector,
        live_runner: LiveConversationRunner,
    ):
        self.store = store
        self.mock_system = mock_system
        self.live_runner = live_runner

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

        if execution_mode != "live":
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
                    "Execution · Deterministic fallback",
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
        required_tool = REQUIRED_TOOLS.get(
            agent_id, (None, request.tool_name or "unavailable")
        )
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
        confidence = 0.98 if verification_mode == "strict" else 0.96
        if verification_mode == "advisory":
            confidence = 0.9
        return OutputVerification(
            status="verified" if complete else "needs_review",
            confidence=confidence if complete else 0.52,
            summary=(
                "The response matches the request and is grounded in the selected tool output."
                if complete
                else "The response needs human review because its supporting evidence is incomplete."
            ),
            criteria=criteria,
            evidence=evidence,
        )
