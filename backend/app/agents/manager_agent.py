from __future__ import annotations

import time
from uuid import uuid4

from backend.app.agents.architecture_agent import ArchitectureAgent
from backend.app.agents.developer_agent import DeveloperAgent
from backend.app.agents.validation_agent import ValidationAgent
from backend.app.core.models import BuildRecord, BuildRequest, StageResult, utc_now
from backend.app.core.storage import JsonStore
from backend.app.infrastructure.llm_router import LLMRouter
from backend.app.infrastructure.tool_runtime import ToolRuntime
from backend.app.infrastructure.workspace_access import WorkspaceAccess


class ManagerAgent:
    def __init__(
        self,
        store: JsonStore,
        architecture_agent: ArchitectureAgent,
        developer_agent: DeveloperAgent,
        validation_agent: ValidationAgent,
        runtime: ToolRuntime,
        llm_router: LLMRouter,
        workspace_access: WorkspaceAccess,
    ):
        self.store = store
        self.architecture_agent = architecture_agent
        self.developer_agent = developer_agent
        self.validation_agent = validation_agent
        self.runtime = runtime
        self.llm_router = llm_router
        self.workspace_access = workspace_access

    async def build(self, request: BuildRequest) -> BuildRecord:
        build = BuildRecord(
            id=f"build_{uuid4().hex[:10]}",
            prompt=request.prompt,
            status="running",
            stages=[
                StageResult(id="introspect", label="Introspect", status="pending", detail="Waiting"),
                StageResult(id="plan", label="Plan reuse", status="pending", detail="Waiting"),
                StageResult(id="generate", label="Generate", status="pending", detail="Waiting"),
                StageResult(id="validate", label="Validate", status="pending", detail="Waiting"),
                StageResult(id="deploy", label="Register", status="pending", detail="Waiting"),
            ],
        )
        self.store.upsert_build(build)

        try:
            architecture = self.store.architecture()
            started = self._start(build, "introspect")
            discovered_agents = await self.architecture_agent.discover_all(architecture)
            self.store.update_agents(discovered_agents)
            architecture = self.store.architecture()
            build.reuse_candidates = self.architecture_agent.search(request.prompt, architecture)
            build.workspace_files = self.workspace_access.search(request.prompt)
            self._pass(build, "introspect", f"Discovered {sum(len(agent.mcp_tools) for agent in discovered_agents)} MCP tools and mapped {len(build.workspace_files)} relevant files.", started)

            started = self._start(build, "plan")
            route = await self.llm_router.route(request.prompt, build.reuse_candidates)
            artifact = self.developer_agent.generate(request.prompt, build.reuse_candidates, route.intent)
            build.plan = artifact.plan
            build.plan["workspace_files"] = [match.model_dump() for match in build.workspace_files]
            build.plan["routing"] = {
                "intent": route.intent,
                "rationale": route.rationale,
                "provider": route.provider,
            }
            build.tool = artifact.tool
            self._pass(build, "plan", f"Routed via {route.provider}; selected {len(artifact.tool.endpoint_ids)} endpoint(s) for reuse.", started)

            started = self._start(build, "generate")
            build.source_code = artifact.source
            self._pass(build, "generate", f"Generated {len(artifact.source.splitlines())} lines of constrained Python.", started)

            started = self._start(build, "validate")
            build.validations = await self.validation_agent.validate(
                artifact.source,
                artifact.tool,
                {endpoint.id for endpoint in architecture.endpoints},
            )
            failed = [check for check in build.validations if check.status == "failed"]
            if failed:
                self._fail(build, "validate", f"{len(failed)} validation check(s) failed.", started)
                self._skip(build, "deploy", "Registration blocked by validation policy.")
                build.status = "failed"
            else:
                self._pass(build, "validate", f"All {len(build.validations)} checks passed.", started)
                started = self._start(build, "deploy")
                if request.deploy:
                    self.runtime.write(artifact.tool.source_file or f"{artifact.tool.id}.py", artifact.source)
                    self.store.register_tool(artifact.tool.model_dump())
                    self._pass(build, "deploy", "Tool registered and continuous monitoring enabled.", started)
                    build.status = "completed"
                else:
                    self._skip(build, "deploy", "Deployment disabled; artifact is awaiting review.")
                    build.status = "awaiting_review"
        except Exception as exc:
            build.status = "failed"
            build.error = str(exc)
            for stage in build.stages:
                if stage.status == "running":
                    stage.status = "failed"
                    stage.detail = str(exc)
                elif stage.status == "pending":
                    stage.status = "skipped"
                    stage.detail = "Skipped after pipeline failure."

        build.completed_at = utc_now()
        self.store.upsert_build(build)
        return build

    @staticmethod
    def _stage(build: BuildRecord, stage_id: str) -> StageResult:
        return next(stage for stage in build.stages if stage.id == stage_id)

    def _start(self, build: BuildRecord, stage_id: str) -> float:
        stage = self._stage(build, stage_id)
        stage.status = "running"
        stage.detail = "In progress"
        self.store.upsert_build(build)
        return time.perf_counter()

    def _pass(self, build: BuildRecord, stage_id: str, detail: str, started: float) -> None:
        stage = self._stage(build, stage_id)
        stage.status = "passed"
        stage.detail = detail
        stage.duration_ms = max(1, round((time.perf_counter() - started) * 1000))
        self.store.upsert_build(build)

    def _fail(self, build: BuildRecord, stage_id: str, detail: str, started: float) -> None:
        stage = self._stage(build, stage_id)
        stage.status = "failed"
        stage.detail = detail
        stage.duration_ms = max(1, round((time.perf_counter() - started) * 1000))

    def _skip(self, build: BuildRecord, stage_id: str, detail: str) -> None:
        stage = self._stage(build, stage_id)
        stage.status = "skipped"
        stage.detail = detail
