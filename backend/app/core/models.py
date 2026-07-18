"""Shared domain contracts used by every backend agent."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentRecord(BaseModel):
    id: str
    name: str
    description: str
    owner: str
    tool_ids: list[str] = Field(default_factory=list)
    status: Literal["healthy", "degraded", "offline"] = "healthy"
    mcp_endpoint: str | None = None
    mcp_server_name: str | None = None
    mcp_tools: list["MCPToolCapability"] = Field(default_factory=list)
    mcp_prompts: list[str] = Field(default_factory=list)
    mcp_resources: list[str] = Field(default_factory=list)
    features: list[str] = Field(default_factory=list)
    last_discovered_at: str | None = None
    instructions: str = ""
    response_style: Literal["concise", "balanced", "detailed"] = "balanced"
    tool_policy: Literal["automatic", "approval", "disabled"] = "automatic"
    enabled_tools: list[str] = Field(default_factory=list)
    verification_mode: Literal["strict", "balanced", "advisory"] = "balanced"
    memory_enabled: bool = True


class AgentUpdateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    description: str = Field(min_length=8, max_length=500)
    owner: str = Field(min_length=2, max_length=100)
    mcp_endpoint: str | None = Field(default=None, max_length=500)
    instructions: str = Field(min_length=12, max_length=4000)
    features: list[str] = Field(default_factory=list, max_length=20)
    response_style: Literal["concise", "balanced", "detailed"] = "balanced"
    tool_policy: Literal["automatic", "approval", "disabled"] = "automatic"
    enabled_tools: list[str] = Field(default_factory=list)
    verification_mode: Literal["strict", "balanced", "advisory"] = "balanced"
    memory_enabled: bool = True

    @field_validator("name", "description", "owner", "instructions")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("mcp_endpoint")
    @classmethod
    def normalize_mcp_endpoint(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        endpoint = value.strip()
        if not endpoint.startswith(("demo://", "http://", "https://")):
            raise ValueError("MCP endpoint must use demo://, http://, or https://")
        return endpoint

    @field_validator("features", "enabled_tools")
    @classmethod
    def normalize_lists(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))


class MCPToolCapability(BaseModel):
    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)


class EndpointRecord(BaseModel):
    id: str
    name: str
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "GET"
    path: str
    description: str
    owner: str
    tags: list[str] = Field(default_factory=list)
    status: Literal["healthy", "degraded", "offline"] = "healthy"
    latency_ms: int = 0


class ToolRecord(BaseModel):
    id: str
    name: str
    description: str
    owner: str
    endpoint_ids: list[str] = Field(default_factory=list)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    generated: bool = False
    status: Literal["healthy", "degraded", "offline"] = "healthy"
    version: str = "1.0.0"
    created_at: str = Field(default_factory=utc_now)
    source_file: str | None = None
    operation: str | None = None
    probe_input: dict[str, Any] = Field(default_factory=dict)


class DataSourceRecord(BaseModel):
    id: str
    name: str
    kind: str
    description: str
    owner: str
    status: Literal["healthy", "degraded", "offline"] = "healthy"


class ArchitectureState(BaseModel):
    agents: list[AgentRecord] = Field(default_factory=list)
    tools: list[ToolRecord] = Field(default_factory=list)
    endpoints: list[EndpointRecord] = Field(default_factory=list)
    data_sources: list[DataSourceRecord] = Field(default_factory=list)
    indexed_at: str = Field(default_factory=utc_now)


class BuildRequest(BaseModel):
    prompt: str = Field(min_length=8, max_length=1000)
    deploy: bool = True

    @field_validator("prompt")
    @classmethod
    def normalize_prompt(cls, value: str) -> str:
        return " ".join(value.split())


class StageResult(BaseModel):
    id: Literal["introspect", "plan", "generate", "validate", "deploy"]
    label: str
    status: Literal["pending", "running", "passed", "failed", "skipped"]
    detail: str
    duration_ms: int = 0


class ReuseCandidate(BaseModel):
    kind: Literal["tool", "endpoint", "data_source", "agent"]
    id: str
    name: str
    description: str
    score: float
    reason: str


class ValidationCheck(BaseModel):
    name: str
    status: Literal["passed", "failed", "warning"]
    detail: str
    duration_ms: int = 0


class BuildRecord(BaseModel):
    id: str
    prompt: str
    status: Literal["running", "completed", "failed", "awaiting_review"]
    created_at: str = Field(default_factory=utc_now)
    completed_at: str | None = None
    stages: list[StageResult] = Field(default_factory=list)
    reuse_candidates: list[ReuseCandidate] = Field(default_factory=list)
    plan: dict[str, Any] = Field(default_factory=dict)
    tool: ToolRecord | None = None
    source_code: str | None = None
    validations: list[ValidationCheck] = Field(default_factory=list)
    workspace_files: list["WorkspaceFileMatch"] = Field(default_factory=list)
    error: str | None = None


class WorkspaceFileMatch(BaseModel):
    path: str
    name: str
    reason: str
    score: float


class WorkspaceEntry(BaseModel):
    path: str
    name: str
    kind: Literal["file", "directory"]
    size: int = 0
    modified_at: str | None = None
    previewable: bool = False


class WorkspaceListing(BaseModel):
    root_name: str
    path: str
    parent: str | None = None
    entries: list[WorkspaceEntry] = Field(default_factory=list)


class WorkspaceFileContent(BaseModel):
    path: str
    name: str
    language: str
    size: int
    content: str
    truncated: bool = False


class ConnectedWorkspace(BaseModel):
    id: str
    name: str
    root_path: str
    agent_id: str | None = None
    writable: bool = False
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)


class ConnectWorkspaceRequest(BaseModel):
    path: str = Field(min_length=1, max_length=2000)
    name: str | None = Field(default=None, max_length=120)
    agent_id: str | None = Field(default=None, max_length=120)
    writable: bool = False

    @field_validator("path")
    @classmethod
    def normalize_path(cls, value: str) -> str:
        return value.strip()

    @field_validator("name", "agent_id")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class HealthResult(BaseModel):
    id: str
    kind: Literal["agent", "tool", "endpoint", "data_source", "manager"]
    name: str
    status: Literal["healthy", "degraded", "offline"]
    latency_ms: int
    checked_at: str = Field(default_factory=utc_now)
    message: str


class ExecuteRequest(BaseModel):
    payload: dict[str, Any]


class ToolCallRecord(BaseModel):
    id: str
    tool_name: str
    tool_id: str | None = None
    status: Literal["passed", "failed"]
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    duration_ms: int = 0


class OutputVerification(BaseModel):
    status: Literal["verified", "needs_review", "failed"]
    confidence: float = Field(ge=0, le=1)
    summary: str
    criteria: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class ChatMessage(BaseModel):
    id: str
    role: Literal["user", "agent"]
    content: str
    created_at: str = Field(default_factory=utc_now)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    verification: OutputVerification | None = None
    context_used: list[str] = Field(default_factory=list)
    execution_mode: Literal["live", "deterministic", "fallback"] = "deterministic"
    provider: str = "local:deterministic"
    endpoint: str | None = None
    fallback_reason: str | None = None


class AgentConversation(BaseModel):
    id: str
    agent_id: str
    title: str
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)
    messages: list[ChatMessage] = Field(default_factory=list)


class AgentChatRequest(BaseModel):
    agent_id: str
    message: str = Field(min_length=2, max_length=2000)
    conversation_id: str | None = None
    context_mode: Literal["minimal", "full"] = "minimal"
    tool_name: str | None = None

    @field_validator("message")
    @classmethod
    def normalize_message(cls, value: str) -> str:
        return " ".join(value.split())


class ManagerAction(BaseModel):
    id: str
    server: Literal["architecture", "workspace", "developer", "validation", "monitoring"]
    tool: str
    status: Literal["running", "passed", "failed"]
    title: str
    detail: str
    duration_ms: int = 0


class ManagerChange(BaseModel):
    id: str
    target: str
    kind: Literal["configuration", "instructions", "tool", "file"]
    summary: str
    before: str
    after: str
    status: Literal["pending", "applied", "rejected"] = "pending"


class ManagerEvaluation(BaseModel):
    status: Literal["passed", "needs_review", "failed"]
    summary: str
    checks: list[str] = Field(default_factory=list)


class ManagerMessage(BaseModel):
    id: str
    role: Literal["user", "manager"]
    content: str
    created_at: str = Field(default_factory=utc_now)
    actions: list[ManagerAction] = Field(default_factory=list)
    changes: list[ManagerChange] = Field(default_factory=list)
    evaluation: ManagerEvaluation | None = None
    provider: str = "local:deterministic"


class ManagerConversation(BaseModel):
    id: str
    agent_id: str
    title: str
    autonomy: Literal["review", "auto"] = "review"
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)
    messages: list[ManagerMessage] = Field(default_factory=list)


class ManagerChatRequest(BaseModel):
    agent_id: str
    message: str = Field(min_length=3, max_length=3000)
    conversation_id: str | None = None
    autonomy: Literal["review", "auto"] = "review"

    @field_validator("message")
    @classmethod
    def normalize_manager_message(cls, value: str) -> str:
        return " ".join(value.split())


class JsonRpcRequest(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: str | int | None = None
    method: str
    params: dict[str, Any] = Field(default_factory=dict)
