"""Standalone FastAPI application entry point."""
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any
from .mcp_server import handle
from .state import AGENT_NAME, AGENT_VERSION

app = FastAPI(title=AGENT_NAME, version=AGENT_VERSION)

class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: str | int | None = None
    method: str
    params: dict[str, Any] = {}

@app.get("/health")
def health() -> dict[str, str]: return {"status": "ok", "agent": AGENT_NAME, "version": AGENT_VERSION}

@app.post("/mcp")
def mcp(request: JsonRpcRequest) -> dict[str, Any]: return handle(request.model_dump())
