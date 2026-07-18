from __future__ import annotations

import time
from uuid import uuid4

from backend.app.agents.architecture_agent import (
    ArchitectureAgent,
    CapabilityMatch,
)
from backend.app.agents.developer_agent import DeveloperAgent
from backend.app.agents.validation_agent import ValidationAgent
from backend.app.core.models import (
    AgentRecord,
    BuildRecord,
    BuildRequest,
    MCPToolCapability,
    StageResult,
    ToolRecord,
    utc_now,
)
from backend.app.core.storage import JsonStore
from backend.app.infrastructure.llm_router import LLMRouter
from backend.app.infrastructure.managed_workspace import ManagedAgentWorkspace
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
        managed_workspace: ManagedAgentWorkspace,
    ):
        self.store = store
        self.architecture_agent = architecture_agent
        self.developer_agent = developer_agent
        self.validation_agent = validation_agent
        self.runtime = runtime
        self.llm_router = llm_router
        self.workspace_access = workspace_access
        self.managed_workspace = managed_workspace

    async def build(self, request: BuildRequest) -> BuildRecord:
        build = BuildRecord(
            id=f"build_{uuid4().hex[:10]}",
            prompt=request.prompt,
            status="running",
            target_agent_id=request.agent_id,
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
            if request.agent_id and not any(
                agent.id == request.agent_id
                for agent in architecture.agents
            ):
                raise ValueError(
                    f"Managed agent not found: {request.agent_id}"
                )
            started = self._start(build, "introspect")
            discovered_agents = await self.architecture_agent.discover_all(architecture)
            self.store.update_agents(discovered_agents)
            for agent in discovered_agents:
                self.managed_workspace.sync(agent)
            architecture = self.store.architecture()
            build.reuse_candidates = self.architecture_agent.search(request.prompt, architecture)
            build.workspace_files = self.workspace_access.search(request.prompt)
            fleet_match = self.architecture_agent.find_capability_match(
                request.prompt,
                architecture,
            )
            self._pass(
                build,
                "introspect",
                (
                    f"Scanned {len(architecture.agents)} agents and "
                    f"{sum(len(agent.mcp_tools) for agent in discovered_agents)} "
                    "agent tools, plus "
                    f"{len(architecture.tools)} registered tools; "
                    + (
                        f"found a {fleet_match.relation} capability match."
                        if fleet_match
                        else "found no capability complete enough to reuse."
                    )
                ),
                started,
            )

            started = self._start(build, "plan")
            if fleet_match:
                self._plan_existing_capability(
                    build,
                    request,
                    architecture.agents,
                    fleet_match,
                    started,
                )
                build.completed_at = utc_now()
                self.store.upsert_build(build)
                return build

            route = await self.llm_router.route(
                request.prompt,
                build.reuse_candidates,
            )
            artifact = self.developer_agent.generate(
                request.prompt,
                build.reuse_candidates,
                route.intent,
            )
            build.plan = artifact.plan
            build.plan["workspace_files"] = [match.model_dump() for match in build.workspace_files]
            build.plan["routing"] = {
                "intent": route.intent,
                "rationale": route.rationale,
                "provider": route.provider,
            }
            build.plan["fleet_preflight"] = {
                "decision": "build",
                "reason": (
                    "The fleet scan found no equivalent or overlapping "
                    "capability complete enough to satisfy this request."
                ),
                "agents_scanned": len(architecture.agents),
                "registered_tools_scanned": len(architecture.tools),
            }
            build.decision = "build"
            build.decision_reason = build.plan["fleet_preflight"]["reason"]
            build.tool = artifact.tool
            conflict = self._registration_conflict(
                artifact.tool,
                architecture.agents,
                request.agent_id,
                architecture.tools,
            )
            if conflict:
                build.decision = "conflict"
                build.decision_reason = conflict
                build.error = conflict
                build.plan["fleet_preflight"] = {
                    "decision": "conflict",
                    "reason": conflict,
                    "agents_scanned": len(architecture.agents),
                    "registered_tools_scanned": len(architecture.tools),
                }
                self._fail(build, "plan", conflict, started)
                self._skip(
                    build,
                    "generate",
                    "Generation blocked by a fleet tool identity conflict.",
                )
                self._skip(
                    build,
                    "validate",
                    "Validation skipped because no artifact was accepted.",
                )
                self._skip(
                    build,
                    "deploy",
                    "Registration blocked to avoid replacing an existing tool.",
                )
                build.status = "failed"
                build.completed_at = utc_now()
                self.store.upsert_build(build)
                return build
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
                    if request.agent_id:
                        capability = self._registered_capability(artifact.tool)
                        self._attach_capability(
                            request.agent_id,
                            capability,
                        )
                        build.attached_agent_ids = [request.agent_id]
                    detail = "Tool registered and continuous monitoring enabled."
                    if request.agent_id:
                        detail += (
                            f" Attached and enabled for {request.agent_id}."
                        )
                    self._pass(build, "deploy", detail, started)
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

    def _plan_existing_capability(
        self,
        build: BuildRecord,
        request: BuildRequest,
        agents: list[AgentRecord],
        match: CapabilityMatch,
        started: float,
    ) -> None:
        target = next(
            (
                agent
                for agent in agents
                if agent.id == request.agent_id
            ),
            None,
        )
        target_has_capability = bool(
            target and target.id in match.source_agent_ids
        )
        should_attach = bool(target and not target_has_capability)
        build.decision = "attach" if should_attach else "reuse"
        build.tool = match.tool
        build.matched_tool_id = match.tool.id
        source_text = (
            ", ".join(match.source_agent_ids)
            if match.source_agent_ids
            else "the manager registry"
        )
        if should_attach:
            build.decision_reason = (
                f"{match.reason} Reusing {match.tool.name} from "
                f"{source_text} avoids a duplicate; it will be attached to "
                f"{target.id}."
            )
        elif target:
            build.decision_reason = (
                f"{match.reason} {target.id} already has "
                f"{match.tool.name}, so no generation or attachment is needed."
            )
        else:
            build.decision_reason = (
                f"{match.reason} Reuse {match.tool.name} from "
                f"{source_text}; generating another copy would duplicate "
                "fleet capability."
            )
        build.plan = {
            "request": request.prompt,
            "strategy": (
                "attach_existing_capability"
                if should_attach
                else "reuse_existing_capability"
            ),
            "target_agent_id": request.agent_id,
            "fleet_preflight": {
                "decision": build.decision,
                "relation": match.relation,
                "score": match.score,
                "matched_tool_id": match.tool.id,
                "matched_tool_name": match.tool.name,
                "source_agent_ids": match.source_agent_ids,
                "provider": match.capability.provider,
                "provider_endpoint": match.capability.provider_endpoint,
                "reason": build.decision_reason,
            },
            "workspace_files": [
                item.model_dump() for item in build.workspace_files
            ],
            "steps": [
                "Scan every registered and agent-discovered capability",
                "Compare the request with fleet tool contracts",
                (
                    "Attach and enable the matching capability"
                    if should_attach
                    else "Keep using the capability already in place"
                ),
            ],
        }
        self._pass(
            build,
            "plan",
            build.decision_reason,
            started,
        )
        self._skip(
            build,
            "generate",
            f"Skipped because {match.tool.name} already covers the request.",
        )
        self._skip(
            build,
            "validate",
            "Skipped generation validation; the existing capability remains unchanged.",
        )

        if should_attach and request.deploy:
            deploy_started = self._start(build, "deploy")
            self._attach_capability(target.id, match.capability)
            build.attached_agent_ids = [target.id]
            self._pass(
                build,
                "deploy",
                (
                    f"Attached and enabled {match.tool.name} for "
                    f"{target.id} using {match.capability.provider}."
                ),
                deploy_started,
            )
            build.status = "completed"
        elif should_attach:
            self._skip(
                build,
                "deploy",
                "Attachment disabled; the reuse plan is awaiting review.",
            )
            build.status = "awaiting_review"
        else:
            self._skip(
                build,
                "deploy",
                "No registration or attachment was required.",
            )
            build.status = "completed"

    def _attach_capability(
        self,
        agent_id: str,
        capability: MCPToolCapability,
    ) -> AgentRecord:
        architecture = self.store.architecture()
        agent = next(
            (item for item in architecture.agents if item.id == agent_id),
            None,
        )
        if agent is None:
            raise ValueError(f"Managed agent not found: {agent_id}")

        same_name = next(
            (
                item
                for item in [
                    *agent.mcp_tools,
                    *agent.attached_tools,
                ]
                if item.name == capability.name
            ),
            None,
        )
        if same_name and same_name.input_schema != capability.input_schema:
            raise ValueError(
                f"Tool conflict on {agent_id}: {capability.name} already "
                "exists with a different input contract"
            )
        if same_name:
            self.managed_workspace.sync(agent)
            return agent

        attached_tools = [*agent.attached_tools, capability]
        mcp_tools = [*agent.mcp_tools, capability]
        enabled_tools = list(
            dict.fromkeys([*agent.enabled_tools, capability.name])
        )
        tool_ids = list(agent.tool_ids)
        if capability.tool_id and self.store.get_tool(capability.tool_id):
            tool_ids = list(
                dict.fromkeys([*tool_ids, capability.tool_id])
            )
        updated = agent.model_copy(
            update={
                "attached_tools": attached_tools,
                "mcp_tools": mcp_tools,
                "enabled_tools": enabled_tools,
                "tool_ids": tool_ids,
            }
        )
        self.store.update_agent(updated)
        self.managed_workspace.sync(updated)
        return updated

    @staticmethod
    def _registered_capability(tool: ToolRecord) -> MCPToolCapability:
        return MCPToolCapability(
            name=tool.name,
            description=tool.description,
            input_schema=tool.input_schema,
            tool_id=tool.id,
            provider="manager_runtime",
        )

    @staticmethod
    def _registration_conflict(
        proposed: ToolRecord,
        agents: list[AgentRecord],
        target_agent_id: str | None,
        registered_tools: list[ToolRecord],
    ) -> str | None:
        registered = next(
            (
                tool
                for tool in registered_tools
                if tool.id == proposed.id or tool.name == proposed.name
            ),
            None,
        )
        if registered:
            return (
                f"Fleet conflict: {proposed.name} would replace registered "
                f"tool {registered.id}, but the semantic preflight did not "
                "find that tool complete enough for this request. Refine the "
                "capability contract or choose a distinct tool identity."
            )
        if not target_agent_id:
            return None
        target = next(
            (
                agent
                for agent in agents
                if agent.id == target_agent_id
            ),
            None,
        )
        if target is None:
            return None
        named = next(
            (
                capability
                for capability in [
                    *target.mcp_tools,
                    *target.attached_tools,
                ]
                if capability.name == proposed.name
            ),
            None,
        )
        if named is None:
            return None
        contract = (
            "a different input contract"
            if named.input_schema != proposed.input_schema
            else "an independently configured provider"
        )
        return (
            f"Agent conflict: {target_agent_id} already exposes "
            f"{proposed.name} through {contract}. Registration was blocked "
            "instead of silently shadowing that capability."
        )

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
