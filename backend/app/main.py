from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes import router as api_router
from backend.app.dependencies import (
    agent_process_manager,
    managed_workspace,
    monitoring_agent,
    settings,
    store,
)
from backend.app.mcp.gateway import router as mcp_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    store.initialize()
    managed_workspace.initialize()
    await monitoring_agent.reconcile_once()
    reconciliation_task = asyncio.create_task(
        monitoring_agent.run_loop(
            settings.reconciliation_interval_seconds
        ),
        name="fleet-reconciliation",
    )
    try:
        yield
    finally:
        agent_process_manager.stop_all()
        reconciliation_task.cancel()
        with suppress(asyncio.CancelledError):
            await reconciliation_task


app = FastAPI(
    title="Agentic AI Manager",
    version="0.1.0",
    description="Introspect, build, validate, register, and monitor agent tools.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.frontend_origins),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)
app.include_router(mcp_router)


@app.get("/", include_in_schema=False)
async def service_info() -> dict[str, str]:
    return {
        "service": "Agentic AI Manager API",
        "status": "operational",
        "docs": "/docs",
    }
