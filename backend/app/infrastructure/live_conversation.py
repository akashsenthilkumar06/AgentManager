"""OpenAI reasoning loop backed by a managed agent's live MCP tools."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable
from uuid import uuid4

import httpx

from backend.app.core.models import (
    AgentRecord,
    ChatMessage,
    MCPToolCapability,
    ToolCallRecord,
)
from backend.app.infrastructure.mcp_client import ManagedAgentMCPClient
from backend.app.infrastructure.openai_provider import OpenAIProvider

RegisteredToolExecutor = Callable[
    [str, dict[str, Any]],
    Awaitable[dict[str, Any]],
]


@dataclass(slots=True)
class LiveConversationResult:
    text: str
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    criteria: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    provider: str = ""


class LiveConversationRunner:
    """Lets an OpenAI model reason over and call a remote agent's MCP tools."""

    def __init__(
        self,
        provider: OpenAIProvider,
        mcp_client: ManagedAgentMCPClient,
        transport: httpx.AsyncBaseTransport | None = None,
        registered_tool_executor: RegisteredToolExecutor | None = None,
    ):
        self.provider = provider
        self.mcp_client = mcp_client
        self.transport = transport
        self.registered_tool_executor = registered_tool_executor

    @property
    def api_key(self) -> str | None:
        return self.provider.api_key

    @api_key.setter
    def api_key(self, value: str | None) -> None:
        self.provider.api_key = value

    @staticmethod
    def is_live_endpoint(agent: AgentRecord) -> bool:
        return bool(
            agent.mcp_endpoint
            and agent.mcp_endpoint.startswith(("http://", "https://"))
        )

    async def run(
        self,
        agent: AgentRecord,
        messages: list[ChatMessage],
    ) -> LiveConversationResult:
        if not self.is_live_endpoint(agent):
            raise ValueError("The selected agent does not use an HTTP(S) MCP endpoint")
        if not self.provider.configured:
            raise ValueError("OPENAI_API_KEY is not configured")
        if not agent.mcp_tools:
            raise ValueError(
                "No live MCP tools are discovered; test the connection first"
            )
        if agent.tool_policy == "disabled":
            raise ValueError("Live MCP tools are disabled by this agent's policy")

        available = [
            tool
            for tool in agent.mcp_tools
            if not agent.enabled_tools or tool.name in agent.enabled_tools
        ]
        if not available:
            raise ValueError("No discovered MCP tools are enabled for this agent")

        tools, names = self._function_tools(available)
        capabilities = {tool.name: tool for tool in available}
        model = agent.openai_model or self.provider.model
        reasoning_effort = (
            agent.openai_reasoning_effort
            or self.provider.reasoning_effort
        )
        input_items: list[dict[str, Any]] = [
            {
                "role": "assistant" if message.role == "agent" else "user",
                "content": message.content[:8000],
            }
            for message in messages[-12:]
        ]
        tool_calls: list[ToolCallRecord] = []
        instructions = (
            f"You are {agent.name}, a managed agent connected to a live MCP server. "
            f"Follow these agent instructions: {agent.instructions} "
            "Use the provided tools whenever the request requires current external "
            "data. Never substitute remembered or demo data for a tool result. "
            "When a result contains source or proof fields, include those exact "
            "values in the final answer so the live execution can be audited."
        )

        async with httpx.AsyncClient(
            timeout=45.0, transport=self.transport
        ) as client:
            for _ in range(6):
                request_body: dict[str, Any] = {
                    "model": model,
                    "instructions": instructions,
                    "input": input_items,
                    "tools": tools,
                    "tool_choice": "auto",
                    "parallel_tool_calls": True,
                    "store": False,
                }
                if reasoning_effort:
                    request_body["reasoning"] = {
                        "effort": reasoning_effort,
                    }
                payload = await self._create_response(
                    client,
                    request_body,
                )
                output = payload.get("output", [])
                if not isinstance(output, list):
                    raise ValueError("OpenAI response output was not a list")
                input_items.extend(
                    item for item in output if isinstance(item, dict)
                )
                requested = [
                    item
                    for item in output
                    if isinstance(item, dict)
                    and item.get("type") == "function_call"
                ]
                if not requested:
                    text = self.provider.output_text(payload)
                    if not text:
                        raise ValueError("Live reasoning loop returned no final text")
                    return self._result(
                        agent,
                        text,
                        tool_calls,
                        model,
                        reasoning_effort,
                    )

                for item in requested:
                    safe_name = str(item.get("name", ""))
                    remote_name = names.get(safe_name)
                    if remote_name is None:
                        raise ValueError(
                            f"Model requested unknown live tool: {safe_name}"
                        )
                    arguments = json.loads(str(item.get("arguments", "{}")))
                    if not isinstance(arguments, dict):
                        raise ValueError("Live tool arguments must be an object")
                    capability = capabilities[remote_name]
                    provider = capability.provider
                    endpoint = (
                        capability.provider_endpoint or agent.mcp_endpoint
                        if provider == "agent_mcp"
                        else (
                            f"local://registered-tools/{capability.tool_id}"
                            if capability.tool_id
                            else "local://registered-tools"
                        )
                    )
                    started = time.perf_counter()
                    try:
                        if provider == "manager_runtime":
                            if (
                                capability.tool_id is None
                                or self.registered_tool_executor is None
                            ):
                                raise ValueError(
                                    f"{remote_name} is not linked to a registered tool"
                                )
                            result = await self.registered_tool_executor(
                                capability.tool_id,
                                arguments,
                            )
                        else:
                            result = await self.mcp_client.call_tool(
                                endpoint or "",
                                remote_name,
                                arguments,
                            )
                        status = "passed"
                        tool_output = result
                    except Exception as exc:
                        status = "failed"
                        tool_output = {"error": str(exc)}
                    tool_calls.append(
                        ToolCallRecord(
                            id=f"call_{uuid4().hex[:10]}",
                            tool_name=remote_name,
                            tool_id=capability.tool_id,
                            status=status,
                            input=arguments,
                            output=tool_output,
                            duration_ms=max(
                                1,
                                round(
                                    (time.perf_counter() - started) * 1000
                                ),
                            ),
                            provider=provider,
                            endpoint=endpoint,
                        )
                    )
                    input_items.append(
                        {
                            "type": "function_call_output",
                            "call_id": item["call_id"],
                            "output": json.dumps(tool_output),
                        }
                    )
        raise ValueError("Live reasoning loop exceeded its six-step limit")

    async def _create_response(
        self,
        client: httpx.AsyncClient,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        return await self.provider.create_response(
            body,
            client=client,
        )

    def _result(
        self,
        agent: AgentRecord,
        text: str,
        tool_calls: list[ToolCallRecord],
        model: str,
        reasoning_effort: str | None,
    ) -> LiveConversationResult:
        endpoint = agent.mcp_endpoint or ""
        evidence = [
            f"Live agent endpoint: {endpoint}",
            (
                f"OpenAI model: {model}; reasoning effort: "
                f"{reasoning_effort or 'provider default'}"
            ),
        ]
        for call in tool_calls:
            source = call.output.get("source")
            proof = call.output.get("proof")
            detail = (
                f"{call.tool_name} returned status={call.status} "
                f"via {call.provider}"
            )
            if call.endpoint:
                detail += f" at {call.endpoint}"
            if source:
                detail += f", source={source}"
            if proof:
                detail += f", proof={proof}"
            evidence.append(detail)
        if not tool_calls:
            evidence.append("The live model answered without requesting an MCP tool")
        return LiveConversationResult(
            text=text,
            tool_calls=tool_calls,
            criteria=[
                "Use the selected agent's configured tool inventory",
                "Call a discovered or attached tool when current data is required",
                "Ground the answer in the real tool execution result",
            ],
            evidence=evidence,
            provider=f"openai:{model}+mcp",
        )

    @staticmethod
    def _function_tools(
        capabilities: list[MCPToolCapability],
    ) -> tuple[list[dict[str, Any]], dict[str, str]]:
        tools: list[dict[str, Any]] = []
        names: dict[str, str] = {}
        for index, capability in enumerate(capabilities):
            base = re.sub(r"[^a-zA-Z0-9_-]", "_", capability.name)[:60]
            if not base or not re.match(r"^[a-zA-Z_]", base):
                base = f"tool_{index}_{base}"
            safe_name = base
            suffix = 2
            while safe_name in names:
                safe_name = f"{base[:57]}_{suffix}"
                suffix += 1
            names[safe_name] = capability.name
            schema = capability.input_schema
            if not isinstance(schema, dict) or schema.get("type") != "object":
                schema = {"type": "object", "properties": {}}
            tools.append(
                {
                    "type": "function",
                    "name": safe_name,
                    "description": capability.description
                    or f"Call the live MCP tool {capability.name}.",
                    "parameters": schema,
                }
            )
        return tools, names
