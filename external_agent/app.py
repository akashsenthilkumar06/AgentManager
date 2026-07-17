"""Standalone MCP agent used to exercise the Manager's live-agent path.

This module deliberately imports nothing from the main Agent Manager backend.
It can be copied to another directory, installed, and run as its own process.
"""

from __future__ import annotations

import json
import os
from typing import Any

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


app = FastAPI(
    title="Standalone Support MCP Agent",
    version="0.1.0",
    description="Independent MCP server with deterministic support-desk tools.",
)


class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: str | int | None = None
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


TICKETS = {
    "TCK-9001": {
        "ticket_id": "TCK-9001",
        "customer": "Northstar Bikes",
        "priority": "urgent",
        "status": "investigating",
        "hours_open": 19,
        "summary": "Checkout requests intermittently fail for EU customers.",
        "owner": "Platform Reliability",
    },
    "TCK-2042": {
        "ticket_id": "TCK-2042",
        "customer": "Juniper Coffee",
        "priority": "normal",
        "status": "waiting_on_customer",
        "hours_open": 6,
        "summary": "Store administrator cannot export the June invoice.",
        "owner": "Billing Support",
    },
}


TOOLS = [
    {
        "name": "support.lookup_ticket",
        "description": (
            "Look up a support ticket by ID. Use this whenever the user asks about "
            "ticket status, priority, ownership, or the reported problem."
        ),
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["ticket_id"],
            "properties": {
                "ticket_id": {
                    "type": "string",
                    "description": "Support ticket ID such as TCK-9001.",
                }
            },
        },
    },
    {
        "name": "support.estimate_resolution",
        "description": (
            "Estimate remaining resolution time for a known support ticket. Use "
            "this after looking up a ticket when the user asks for an ETA or SLA risk."
        ),
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["ticket_id"],
            "properties": {
                "ticket_id": {
                    "type": "string",
                    "description": "Support ticket ID such as TCK-9001.",
                }
            },
        },
    },
]


@app.get("/")
async def service_info() -> dict[str, Any]:
    return {
        "service": "Standalone Support MCP Agent",
        "status": "operational",
        "mcp_endpoint": "/mcp",
        "tools": [tool["name"] for tool in TOOLS],
        "provenance": "standalone-external-agent",
    }


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy", "provenance": "standalone-external-agent"}


@app.post("/mcp")
async def mcp(request: JsonRpcRequest) -> JSONResponse:
    if request.jsonrpc != "2.0":
        return _error(request.id, -32600, "Only JSON-RPC 2.0 is supported")

    try:
        if request.method == "initialize":
            result: dict[str, Any] = {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {
                    "name": "standalone-support-agent",
                    "version": "0.1.0",
                },
            }
        elif request.method == "tools/list":
            result = {"tools": TOOLS}
        elif request.method == "tools/call":
            result = _call_tool(request.params)
        else:
            return _error(
                request.id,
                -32601,
                f"Unsupported method: {request.method}",
            )
        return JSONResponse(
            {"jsonrpc": "2.0", "id": request.id, "result": result}
        )
    except KeyError as exc:
        return _error(request.id, -32602, f"Missing argument: {exc.args[0]}")
    except ValueError as exc:
        return _error(request.id, -32602, str(exc))


def _call_tool(params: dict[str, Any]) -> dict[str, Any]:
    name = str(params.get("name", ""))
    arguments = params.get("arguments", {})
    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be an object")

    ticket_id = str(arguments.get("ticket_id", "")).strip().upper()
    if not ticket_id:
        raise ValueError("ticket_id is required")
    ticket = TICKETS.get(ticket_id)
    if ticket is None:
        raise ValueError(f"Unknown support ticket: {ticket_id}")

    if name == "support.lookup_ticket":
        output = {
            **ticket,
            "source": "standalone-external-agent",
            "proof": f"LIVE-MCP-{ticket_id}",
        }
    elif name == "support.estimate_resolution":
        remaining_hours = 3 if ticket["priority"] == "urgent" else 16
        sla_limit = 24 if ticket["priority"] == "urgent" else 72
        output = {
            "ticket_id": ticket_id,
            "estimated_hours_remaining": remaining_hours,
            "sla_limit_hours": sla_limit,
            "hours_open": ticket["hours_open"],
            "sla_at_risk": ticket["hours_open"] + remaining_hours >= sla_limit,
            "basis": (
                "Urgent platform incident with an active reliability owner."
                if ticket["priority"] == "urgent"
                else "Normal-priority support request awaiting customer input."
            ),
            "source": "standalone-external-agent",
            "proof": f"LIVE-MCP-ETA-{ticket_id}",
        }
    else:
        raise ValueError(f"Unknown tool: {name}")

    return {
        "content": [{"type": "text", "text": json.dumps(output)}],
        "isError": False,
    }


def _error(
    request_id: str | int | None,
    code: int,
    message: str,
) -> JSONResponse:
    return JSONResponse(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }
    )


if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host=os.getenv("EXTERNAL_AGENT_HOST", "127.0.0.1"),
        port=int(os.getenv("EXTERNAL_AGENT_PORT", "8100")),
        reload=False,
    )
