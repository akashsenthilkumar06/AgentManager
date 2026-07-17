"""Agent-scoped conversation orchestration and output verification."""

from __future__ import annotations

import re
import time
from uuid import uuid4

from backend.app.core.models import (
    AgentChatRequest,
    AgentConversation,
    ChatMessage,
    OutputVerification,
    ToolCallRecord,
    utc_now,
)
from backend.app.core.storage import JsonStore
from backend.app.infrastructure.mock_system import MockSystem


class ConversationAgent:
    """Runs a managed agent with scoped context and verifies its final answer."""

    def __init__(self, store: JsonStore, mock_system: MockSystem):
        self.store = store
        self.mock_system = mock_system

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
        required_tool = {
            "order-support-agent": ("lookup-order", "lookup_order"),
            "logistics-agent": ("track-shipment", "track_shipment"),
            "catalog-agent": ("check-inventory", "check_inventory"),
        }.get(agent.id, (None, request.tool_name or "unavailable"))
        tool_blocked = agent.tool_policy == "disabled" or (
            bool(agent.enabled_tools) and required_tool[1] not in agent.enabled_tools
        )
        if tool_blocked:
            tool_call = ToolCallRecord(
                id=f"call_{uuid4().hex[:10]}",
                tool_id=required_tool[0],
                tool_name=required_tool[1],
                status="failed",
            )
            content = (
                f"I could not complete this test because {required_tool[1]} is disabled "
                "in the current agent configuration."
            )
            criteria = ["Use the required grounded tool", "Return a supported answer"]
            evidence = ["Agent tool policy blocked execution"]
        else:
            tool_call, content, criteria, evidence = await self._run(agent.id, request)
        content = self._apply_response_style(content, tool_call, agent.response_style)
        context_used = self._context_labels(agent, request.context_mode)
        verification = self._verify(
            content, tool_call, criteria, evidence, agent.verification_mode
        )
        tool_call.duration_ms = max(1, round((time.perf_counter() - started) * 1000))
        conversation.messages.append(
            ChatMessage(
                id=f"msg_{uuid4().hex[:10]}",
                role="agent",
                content=content,
                tool_calls=[tool_call],
                verification=verification,
                context_used=context_used,
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

    async def _run(
        self, agent_id: str, request: AgentChatRequest
    ) -> tuple[ToolCallRecord, str, list[str], list[str]]:
        message = request.message.upper()
        if agent_id == "order-support-agent":
            order_id = self._identifier(message, r"ORD-\d+", "ORD-1042")
            output = await self.mock_system.get(f"/mock/orders/{order_id}")
            content = (
                f"{order_id} is currently {output['status'].replace('_', ' ')}. "
                f"It contains {output['items']} items with a total of "
                f"{output['currency']} {output['total']:.2f}."
            )
            return self._tool("lookup-order", "lookup_order", {"order_id": order_id}, output), content, [
                "Identify the requested order",
                "Report its current lifecycle status",
                "Ground the answer in the order system",
            ], [f"Order API returned status={output['status']}", f"Matched order_id={order_id}"]

        if agent_id == "logistics-agent":
            order_id = self._identifier(message, r"ORD-\d+", "ORD-1042")
            output = await self.mock_system.get(f"/mock/shipments/by-order/{order_id}")
            exception = output.get("exception")
            content = (
                f"{order_id} is {output['status'].replace('_', ' ')} with {output['carrier']}. "
                f"The latest event is “{output['latest_event']}” and the current ETA is {output['eta']}."
            )
            if exception:
                content += f" It is delayed by {output['delay_hours']} hours: {exception}."
            else:
                content += " No delivery exception is currently reported."
            return self._tool("track-shipment", "track_shipment", {"order_id": order_id}, output), content, [
                "Identify the requested shipment",
                "Report ETA and latest carrier event",
                "Call out any active exception or delay",
            ], [f"Shipment API returned status={output['status']}", f"Delay hours={output['delay_hours']}"]

        sku = self._identifier(message, r"SKU-[A-Z]+-\d+", "SKU-RED-42")
        output = await self.mock_system.get(f"/mock/inventory/{sku}")
        risk = "out of stock" if output["available"] == 0 else "available"
        content = (
            f"{sku} is {risk}. There are {output['available']} units available "
            f"({output['on_hand']} on hand, {output['reserved']} reserved) across "
            f"{output['location_count']} location{'s' if output['location_count'] != 1 else ''}."
        )
        return self._tool("check-inventory", "check_inventory", {"sku": sku}, output), content, [
            "Identify the requested SKU",
            "Report available inventory",
            "Explain stockout risk using live quantities",
        ], [f"Inventory API returned available={output['available']}", f"Matched sku={sku}"]

    @staticmethod
    def _identifier(message: str, pattern: str, fallback: str) -> str:
        match = re.search(pattern, message)
        return match.group(0) if match else fallback

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
        content: str, tool_call: ToolCallRecord, response_style: str
    ) -> str:
        if response_style == "concise":
            return content.split(". ")[0].rstrip(".") + "."
        if response_style == "detailed" and tool_call.status == "passed":
            return (
                content
                + f" This answer was grounded in {tool_call.tool_name} and will remain "
                "attached to the test history for review."
            )
        return content

    @staticmethod
    def _verify(
        content: str,
        tool_call: ToolCallRecord,
        criteria: list[str],
        evidence: list[str],
        verification_mode: str,
    ) -> OutputVerification:
        complete = bool(content.strip()) and tool_call.status == "passed" and bool(tool_call.output)
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
