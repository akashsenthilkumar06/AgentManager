"""OpenAI reasoning loop backed by a managed agent's live MCP tools."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import httpx

from backend.app.core.models import (
    AgentRecord,
    ChatMessage,
    MCPToolCapability,
    ToolCallRecord,
)
from backend.app.infrastructure.mcp_client import ManagedAgentMCPClient


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
        api_key: str | None,
        model: str,
        base_url: str,
        mcp_client: ManagedAgentMCPClient,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.mcp_client = mcp_client
        self.transport = transport

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
        if not self.api_key:
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
                payload = await self._create_response(
                    client,
                    {
                        "model": self.model,
                        "instructions": instructions,
                        "input": input_items,
                        "tools": tools,
                        "tool_choice": "auto",
                        "parallel_tool_calls": True,
                        "store": False,
                    },
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
                    text = self._output_text(payload)
                    if not text:
                        raise ValueError("Live reasoning loop returned no final text")
                    return self._result(
                        agent, text, tool_calls
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
                    started = time.perf_counter()
                    try:
                        result = await self.mcp_client.call_tool(
                            agent.mcp_endpoint or "",
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
                            status=status,
                            input=arguments,
                            output=tool_output,
                            duration_ms=max(
                                1,
                                round(
                                    (time.perf_counter() - started) * 1000
                                ),
                            ),
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
        response = await client.post(
            f"{self.base_url}/responses",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=body,
        )
        response.raise_for_status()
        return response.json()

    def _result(
        self,
        agent: AgentRecord,
        text: str,
        tool_calls: list[ToolCallRecord],
    ) -> LiveConversationResult:
        endpoint = agent.mcp_endpoint or ""
        evidence = [f"Live MCP endpoint: {endpoint}"]
        for call in tool_calls:
            source = call.output.get("source")
            proof = call.output.get("proof")
            detail = f"{call.tool_name} returned status={call.status}"
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
                "Use the configured external MCP endpoint",
                "Call a discovered live tool when current data is required",
                "Ground the answer in the returned MCP evidence",
            ],
            evidence=evidence,
            provider=f"openai:{self.model}+mcp",
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

    @staticmethod
    def _output_text(payload: dict[str, Any]) -> str:
        direct = payload.get("output_text")
        if isinstance(direct, str) and direct.strip():
            return direct.strip()
        for item in payload.get("output", []):
            if not isinstance(item, dict):
                continue
            for content in item.get("content", []):
                if (
                    isinstance(content, dict)
                    and content.get("type") == "output_text"
                    and isinstance(content.get("text"), str)
                ):
                    return content["text"].strip()
        return ""
