"""OpenAI Responses API tool loop for the Manager Agent."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import httpx


ToolExecutor = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass(slots=True)
class ManagerLoopResult:
    text: str
    provider: str
    calls: list[dict[str, Any]] = field(default_factory=list)


class OpenAIManagerLoop:
    """Lets the model choose and chain Manager tools, with a no-key fallback."""

    TOOLS = [
        {
            "type": "function",
            "name": "architecture_search",
            "description": "Use the Architecture MCP tool to inspect existing agents, tools, endpoints, and reusable patterns relevant to a proposed agent change.",
            "strict": True,
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "required": ["prompt"],
                "properties": {"prompt": {"type": "string"}},
            },
        },
        {
            "type": "function",
            "name": "workspace_inspect",
            "description": "Inspect the selected client agent's local workspace files and current MCP-derived configuration before proposing edits.",
            "strict": True,
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "required": [],
                "properties": {},
            },
        },
        {
            "type": "function",
            "name": "developer_propose_change",
            "description": "Prepare a concrete, minimal change to the selected agent instructions after architecture and workspace inspection.",
            "strict": True,
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "required": ["objective", "instructions_append"],
                "properties": {
                    "objective": {"type": "string"},
                    "instructions_append": {"type": "string"},
                },
            },
        },
        {
            "type": "function",
            "name": "validation_evaluate",
            "description": "Evaluate whether the proposed client-agent change addresses the user's objective and remains grounded in available capabilities.",
            "strict": True,
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "required": ["objective"],
                "properties": {"objective": {"type": "string"}},
            },
        },
    ]

    def __init__(self, api_key: str | None, model: str, base_url: str):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")

    async def run(
        self,
        prompt: str,
        agent_context: dict[str, Any],
        execute: ToolExecutor,
    ) -> ManagerLoopResult | None:
        if not self.api_key:
            return None
        input_items: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": json.dumps(
                    {"request": prompt, "selected_client_agent": agent_context}
                ),
            }
        ]
        calls: list[dict[str, Any]] = []
        instructions = (
            "You are the Manager Agent in an agent-development workspace. "
            "Analyze the requested change, choose the smallest useful MCP-backed tools, "
            "inspect before editing, propose a precise change, and validate it. "
            "Do not claim a change was applied; the application controls approval and writes. "
            "Finish with a concise explanation of what you inspected and changed."
        )
        try:
            async with httpx.AsyncClient(timeout=35.0) as client:
                for _ in range(5):
                    response = await client.post(
                        f"{self.base_url}/responses",
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": self.model,
                            "instructions": instructions,
                            "input": input_items,
                            "tools": self.TOOLS,
                            "tool_choice": "auto",
                            "parallel_tool_calls": True,
                        },
                    )
                    response.raise_for_status()
                    payload = response.json()
                    output = payload.get("output", [])
                    if isinstance(output, list):
                        input_items.extend(output)
                    function_calls = [
                        item
                        for item in output
                        if isinstance(item, dict)
                        and item.get("type") == "function_call"
                    ]
                    if not function_calls:
                        return ManagerLoopResult(
                            text=self._output_text(payload),
                            provider=f"openai:{self.model}",
                            calls=calls,
                        )
                    for item in function_calls:
                        name = str(item.get("name", ""))
                        arguments = json.loads(str(item.get("arguments", "{}")))
                        result = await execute(name, arguments)
                        calls.append(
                            {"name": name, "arguments": arguments, "result": result}
                        )
                        input_items.append(
                            {
                                "type": "function_call_output",
                                "call_id": item["call_id"],
                                "output": json.dumps(result),
                            }
                        )
            return ManagerLoopResult(
                text="I inspected the selected agent, prepared a change, and validated the proposal.",
                provider=f"openai:{self.model}",
                calls=calls,
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

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
        return "I completed the requested agent analysis and prepared the validated change."
