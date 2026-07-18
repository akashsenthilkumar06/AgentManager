"""Standalone FastAPI application and directly runnable entry point."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from dotenv import load_dotenv
from pydantic import BaseModel

# Credentials belong to this independently managed agent, not to the Manager
# control plane. The process manager withholds control-plane secrets, then the
# agent loads only the environment file inside its own selected workspace.
load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

if __package__ in {None, ""}:
    # Agent Manager executes saved commands from this directory. Supporting
    # ``python app.py`` keeps detected/imported entrypoints directly runnable.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from finance_agent.mcp_server import handle
    from finance_agent.state import AGENT_NAME, AGENT_VERSION
else:
    from .mcp_server import handle
    from .state import AGENT_NAME, AGENT_VERSION


app = FastAPI(title=AGENT_NAME, version=AGENT_VERSION)


class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: str | int | None = None
    method: str
    params: dict[str, Any] = {}


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "agent": AGENT_NAME,
        "version": AGENT_VERSION,
    }


@app.post("/mcp")
def mcp(request: JsonRpcRequest) -> dict[str, Any]:
    return handle(request.model_dump())


def main() -> None:
    """Run the independent service using import-safe package state."""
    import uvicorn

    host = os.getenv("FINANCE_AGENT_HOST", "127.0.0.1")
    raw_port = os.getenv("FINANCE_AGENT_PORT", "8080")
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise ValueError(
            "FINANCE_AGENT_PORT must be an integer"
        ) from exc
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
