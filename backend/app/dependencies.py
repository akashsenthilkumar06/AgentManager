"""Application composition root.

Every long-lived backend dependency is created here, keeping transport modules
free of construction logic and making each agent independently testable.
"""

from backend.app.agents.architecture_agent import ArchitectureAgent
from backend.app.agents.agentic_manager import AgenticManager
from backend.app.agents.benchmark_agent import BenchmarkAgent
from backend.app.agents.conversation_agent import ConversationAgent
from backend.app.agents.developer_agent import DeveloperAgent
from backend.app.agents.import_agent import ImportAgent
from backend.app.agents.manager_agent import ManagerAgent
from backend.app.agents.monitoring_agent import MonitoringAgent
from backend.app.agents.validation_agent import ValidationAgent
from backend.app.config import Settings
from backend.app.core.models import ToolRecord
from backend.app.core.storage import JsonStore
from backend.app.infrastructure.llm_router import LLMRouter
from backend.app.infrastructure.agent_process import AgentProcessManager
from backend.app.infrastructure.live_conversation import LiveConversationRunner
from backend.app.infrastructure.managed_workspace import ManagedAgentWorkspace
from backend.app.infrastructure.mcp_client import ManagedAgentMCPClient
from backend.app.infrastructure.mock_system import MockSystem
from backend.app.infrastructure.openai_manager import OpenAIManagerLoop
from backend.app.infrastructure.openai_provider import OpenAIProvider
from backend.app.infrastructure.tool_runtime import ToolRuntime
from backend.app.infrastructure.workspace_access import WorkspaceAccess


settings = Settings.from_env()
store = JsonStore(settings.data_dir / "state.json")
mock_system = MockSystem()
runtime = ToolRuntime(settings.generated_dir)
mcp_client = ManagedAgentMCPClient()
workspace_access = WorkspaceAccess(settings.workspace_root)
managed_workspace = ManagedAgentWorkspace(store, workspace_access)
agent_process_manager = AgentProcessManager()
openai_provider = OpenAIProvider(
    settings.openai_api_key,
    settings.openai_model,
    settings.openai_base_url,
    organization_id=settings.openai_organization_id,
    project_id=settings.openai_project_id,
    reasoning_effort=settings.openai_reasoning_effort,
    max_output_tokens=settings.openai_max_output_tokens,
    timeout_seconds=settings.openai_request_timeout_seconds,
    max_retries=settings.openai_max_retries,
    safety_identifier=settings.openai_safety_identifier,
)


async def execute_registered_tool(
    tool_id: str,
    payload: dict,
) -> dict:
    tool_data = store.get_tool(tool_id)
    if tool_data is None:
        raise ValueError(f"Registered tool not found: {tool_id}")
    tool = ToolRecord.model_validate(tool_data)
    return await runtime.execute_registered(
        tool,
        payload,
        mock_system.get,
        mock_system.execute_operation,
    )


architecture_agent = ArchitectureAgent(mcp_client)
import_agent = ImportAgent(
    store,
    architecture_agent,
    workspace_access,
    managed_workspace,
    agent_process_manager,
)
benchmark_agent = BenchmarkAgent(
    store,
    mcp_client,
    execute_registered_tool,
)
developer_agent = DeveloperAgent()
validation_agent = ValidationAgent(runtime, mock_system)
monitoring_agent = MonitoringAgent(
    runtime,
    mock_system,
    store,
    architecture_agent,
    managed_workspace,
)
llm_router = LLMRouter(openai_provider)
manager_agent = ManagerAgent(
    store,
    architecture_agent,
    developer_agent,
    validation_agent,
    runtime,
    llm_router,
    workspace_access,
    managed_workspace,
)
live_conversation_runner = LiveConversationRunner(
    openai_provider,
    mcp_client,
    registered_tool_executor=execute_registered_tool,
)
conversation_agent = ConversationAgent(
    store,
    mock_system,
    live_conversation_runner,
)
openai_manager_loop = OpenAIManagerLoop(openai_provider)
agentic_manager = AgenticManager(
    store,
    architecture_agent,
    managed_workspace,
    openai_manager_loop,
)
