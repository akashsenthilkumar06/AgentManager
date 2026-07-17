from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes import router as api_router
from backend.app.dependencies import architecture_agent, managed_workspace, settings, store
from backend.app.mcp.gateway import router as mcp_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    store.initialize()
    store.update_agents(await architecture_agent.discover_all(store.architecture()))
    managed_workspace.initialize()
    yield


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
