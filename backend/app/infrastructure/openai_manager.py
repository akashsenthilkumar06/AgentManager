"""OpenAI Responses API tool loop for the Manager Agent."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from backend.app.infrastructure.openai_provider import (
    OpenAIProvider,
    OpenAIProviderError,
)


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
            "description": "Delegate to the Architecture Analyst employee to inspect existing agents, tools, endpoints, and reusable patterns relevant to a proposed agent change.",
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
            "description": "Delegate to the Workspace Inspector employee to inspect the selected client agent's local workspace files and current MCP-derived configuration before proposing edits.",
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
            "name": "workspace_write_file",
            "description": "Create or replace one source/text file in the selected imported agent's real directory. Use only when the user explicitly asks to create or edit a file and Auto permission is active.",
            "strict": True,
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "required": ["path", "content"],
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path such as hello.py.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Complete UTF-8 file contents.",
                    },
                },
            },
        },
        {
            "type": "function",
            "name": "workspace_run_python_file",
            "description": "Run one Python source file in the selected imported agent's real directory and capture stdout and exit status. Use after writing a Python file when execution evidence is requested.",
            "strict": True,
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "required": ["path"],
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative Python file path.",
                    },
                },
            },
        },
        {
            "type": "function",
            "name": "runtime_status",
            "description": "Ask the Runtime Operator for the selected agent's process, scoped workspace, endpoint, and discovered-tool status.",
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
            "name": "runtime_start",
            "description": "Start the selected imported agent with its saved command and wait for its MCP endpoint. Use only for an explicit run, launch, boot, or ensure-live request.",
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
            "name": "runtime_stop",
            "description": "Stop the selected imported agent's managed process group. Use only when the user explicitly asks to stop or shut it down.",
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
            "name": "runtime_discover",
            "description": "Connect to the selected agent's MCP endpoint and refresh the tools it really advertises. For an imported local agent that is not listening yet, the runtime operator automatically launches its saved run command in the background.",
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
            "name": "runtime_call_tool",
            "description": "Call a real enabled MCP tool on the selected agent when the user explicitly requests execution.",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "required": ["tool_name", "arguments"],
                "properties": {
                    "tool_name": {"type": "string"},
                    "arguments": {
                        "type": "object",
                        "additionalProperties": True,
                    },
                },
            },
        },
        {
            "type": "function",
            "name": "developer_propose_change",
            "description": "Delegate to the Developer Specialist employee to prepare a concrete, minimal change to the selected agent instructions after architecture and workspace inspection.",
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
            "description": "Delegate to the Validation Specialist employee to evaluate whether the proposed client-agent change addresses the user's objective and remains grounded in available capabilities.",
            "strict": True,
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "required": ["objective"],
                "properties": {"objective": {"type": "string"}},
            },
        },
    ]

    def __init__(self, provider: OpenAIProvider):
        self.provider = provider

    async def run(
        self,
        prompt: str,
        agent_context: dict[str, Any],
        execute: ToolExecutor,
    ) -> ManagerLoopResult | None:
        if not self.provider.configured:
            return None
        model = (
            agent_context.get("openai_model")
            or self.provider.model
        )
        reasoning_effort = (
            agent_context.get("openai_reasoning_effort")
            or self.provider.reasoning_effort
        )
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
            "Run your specialist employees deliberately: Architecture Analyst, Workspace Inspector, "
            "Developer Specialist, Validation Specialist, and Runtime Operator. "
            "Analyze the request and choose the smallest useful MCP-backed tools. "
            "For behavior changes, inspect before editing, propose a precise change, "
            "and validate it. For runtime requests, inspect, launch, discover, call, "
            "or stop the independent agent with runtime tools; do not create an "
            "instructions edit unless the user also requested a behavior change. "
            "For explicit source-file requests on imported agents, inspect first, "
            "then use workspace_write_file and run the Python file when verification "
            "is requested. Greetings, questions, and status checks are not edit "
            "requests: answer them without proposing an instructions change. "
            "Do not claim a change was applied; the application controls approval and writes. "
            "Finish with a concise explanation grounded in returned process and tool evidence."
        )
        try:
            for _ in range(5):
                request_body: dict[str, Any] = {
                    "model": model,
                    "instructions": instructions,
                    "input": input_items,
                    "tools": self.TOOLS,
                    "tool_choice": "auto",
                    "parallel_tool_calls": True,
                }
                if reasoning_effort:
                    request_body["reasoning"] = {
                        "effort": reasoning_effort,
                    }
                payload = await self.provider.create_response(
                    request_body
                )
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
                        text=self.provider.output_text(payload),
                        provider=f"openai:{model}",
                        calls=calls,
                    )
                for item in function_calls:
                    name = str(item.get("name", ""))
                    arguments = json.loads(
                        str(item.get("arguments", "{}"))
                    )
                    result = await execute(name, arguments)
                    calls.append(
                        {
                            "name": name,
                            "arguments": arguments,
                            "result": result,
                        }
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
                provider=f"openai:{model}",
                calls=calls,
            )
        except (
            OpenAIProviderError,
            KeyError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ):
            return None
