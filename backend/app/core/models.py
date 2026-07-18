"""Shared domain contracts used by every backend agent."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from backend.app.core.openai_models import (
    OPENAI_MODEL_IDS,
    OPENAI_REASONING_EFFORTS,
)


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
    attached_tools: list["MCPToolCapability"] = Field(default_factory=list)
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
    openai_model: str | None = None
    openai_reasoning_effort: str | None = None
    imported: bool = False
    workspace_id: str | None = None
    workspace_root: str | None = None
    run_command: str | None = None
    detected_entrypoints: list[str] = Field(default_factory=list)


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
    openai_model: str | None = None
    openai_reasoning_effort: str | None = None

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

    @field_validator("openai_model")
    @classmethod
    def validate_openai_model(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        model = value.strip()
        if model not in OPENAI_MODEL_IDS:
            raise ValueError(
                "OpenAI model must be gpt-5.6-sol, gpt-5.6-terra, "
                "or gpt-5.6-luna"
            )
        return model

    @field_validator("openai_reasoning_effort")
    @classmethod
    def validate_openai_reasoning_effort(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None or not value.strip():
            return None
        effort = value.strip()
        if effort not in OPENAI_REASONING_EFFORTS:
            raise ValueError(
                "OpenAI reasoning effort must be none, low, medium, high, "
                "xhigh, or max"
            )
        return effort


class AgentImportRequest(BaseModel):
    path: str = Field(min_length=1, max_length=2000)
    name: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    owner: str = Field(default="Local workspace", min_length=2, max_length=100)
    run_command: str | None = Field(default=None, max_length=1000)
    mcp_endpoint: str | None = Field(default=None, max_length=500)
    start_after_import: bool = False

    @field_validator(
        "path",
        "name",
        "description",
        "owner",
        "run_command",
        "mcp_endpoint",
    )
    @classmethod
    def normalize_import_text(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("mcp_endpoint")
    @classmethod
    def validate_import_endpoint(
        cls,
        value: str | None,
    ) -> str | None:
        if value and not value.startswith(
            ("demo://", "http://", "https://")
        ):
            raise ValueError(
                "MCP endpoint must use demo://, http://, or https://"
            )
        return value


class AgentProcessStartRequest(BaseModel):
    command: str | None = Field(default=None, max_length=1000)

    @field_validator("command")
    @classmethod
    def normalize_process_command(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class MCPToolCapability(BaseModel):
    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)
    tool_id: str | None = None
    provider: Literal["agent_mcp", "manager_runtime"] = "agent_mcp"
    provider_endpoint: str | None = None


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
    agent_id: str | None = Field(default=None, max_length=120)

    @field_validator("prompt")
    @classmethod
    def normalize_prompt(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("agent_id")
    @classmethod
    def normalize_agent_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


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
    target_agent_id: str | None = None
    decision: Literal["build", "reuse", "attach", "conflict"] = "build"
    decision_reason: str = ""
    matched_tool_id: str | None = None
    attached_agent_ids: list[str] = Field(default_factory=list)


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


class FindingTrigger(BaseModel):
    agent: str = "ArchitectureAgent"
    action: str = "architecture.search"
    status: Literal["triggered", "completed", "failed"] = "triggered"
    detail: str = ""
    related_component_ids: list[str] = Field(default_factory=list)


class ReconciliationFinding(BaseModel):
    id: str
    key: str
    kind: Literal[
        "capability_drift",
        "duplicate_capability",
        "capability_conflict",
        "endpoint_health",
        "component_health",
    ]
    severity: Literal["info", "warning", "critical"]
    status: Literal["open", "observed", "resolved"] = "open"
    origin: Literal["standing_reconciliation"] = "standing_reconciliation"
    title: str
    detail: str
    why_it_matters: str
    agent_ids: list[str] = Field(default_factory=list)
    tool_names: list[str] = Field(default_factory=list)
    before: dict[str, Any] = Field(default_factory=dict)
    after: dict[str, Any] = Field(default_factory=dict)
    detected_at: str = Field(default_factory=utc_now)
    last_seen_at: str = Field(default_factory=utc_now)
    resolved_at: str | None = None
    occurrences: int = 1
    trigger: FindingTrigger | None = None


class BenchmarkRequest(BaseModel):
    agent_id: str


class BenchmarkMetric(BaseModel):
    id: Literal[
        "overall_score",
        "task_success",
        "tool_coverage",
        "grounding_rate",
        "verification_rate",
        "average_latency",
    ]
    label: str
    unit: Literal["percent", "milliseconds"]
    higher_is_better: bool = True
    baseline: float
    managed: float


class BenchmarkSideResult(BaseModel):
    status: Literal["passed", "failed", "unavailable"]
    tool_name: str
    provider: str | None = None
    latency_ms: int = 0
    output_keys: list[str] = Field(default_factory=list)
    error: str | None = None


class BenchmarkScenarioResult(BaseModel):
    id: str
    title: str
    objective: str
    required_tool: str
    probe_input: dict[str, Any] = Field(default_factory=dict)
    baseline: BenchmarkSideResult
    managed: BenchmarkSideResult


class BenchmarkRun(BaseModel):
    id: str
    agent_id: str
    agent_name: str
    status: Literal["completed", "failed"] = "completed"
    created_at: str = Field(default_factory=utc_now)
    baseline_label: str = "Without Agentic Manager"
    managed_label: str = "With Agentic Manager"
    summary: str
    metrics: list[BenchmarkMetric] = Field(default_factory=list)
    scenarios: list[BenchmarkScenarioResult] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    error: str | None = None


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
    provider: Literal[
        "agent_mcp",
        "manager_runtime",
        "deterministic",
    ] = "deterministic"
    endpoint: str | None = None


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
    server: Literal[
        "architecture",
        "workspace",
        "developer",
        "validation",
        "monitoring",
        "runtime",
    ]
    tool: str
    status: Literal["running", "passed", "failed"]
    title: str
    detail: str
    duration_ms: int = 0
    evidence: dict[str, Any] = Field(default_factory=dict)


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
