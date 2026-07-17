"""Application composition root.

Every long-lived backend dependency is created here, keeping transport modules
free of construction logic and making each agent independently testable.
"""

from backend.app.agents.architecture_agent import ArchitectureAgent
from backend.app.agents.agentic_manager import AgenticManager
from backend.app.agents.conversation_agent import ConversationAgent
from backend.app.agents.developer_agent import DeveloperAgent
from backend.app.agents.manager_agent import ManagerAgent
from backend.app.agents.monitoring_agent import MonitoringAgent
from backend.app.agents.validation_agent import ValidationAgent
from backend.app.config import Settings
from backend.app.core.storage import JsonStore
from backend.app.infrastructure.llm_router import LLMRouter
from backend.app.infrastructure.live_conversation import LiveConversationRunner
from backend.app.infrastructure.managed_workspace import ManagedAgentWorkspace
from backend.app.infrastructure.mcp_client import ManagedAgentMCPClient
from backend.app.infrastructure.mock_system import MockSystem
from backend.app.infrastructure.openai_manager import OpenAIManagerLoop
from backend.app.infrastructure.tool_runtime import ToolRuntime
from backend.app.infrastructure.workspace_access import WorkspaceAccess


settings = Settings.from_env()
store = JsonStore(settings.data_dir / "state.json")
mock_system = MockSystem()
runtime = ToolRuntime(settings.generated_dir)
mcp_client = ManagedAgentMCPClient()
workspace_access = WorkspaceAccess(settings.workspace_root)
managed_workspace = ManagedAgentWorkspace(store)

architecture_agent = ArchitectureAgent(mcp_client)
developer_agent = DeveloperAgent()
validation_agent = ValidationAgent(runtime, mock_system)
monitoring_agent = MonitoringAgent(runtime, mock_system)
llm_router = LLMRouter(
    settings.openai_api_key,
    settings.openai_model,
    settings.openai_base_url,
)
manager_agent = ManagerAgent(
    store,
    architecture_agent,
    developer_agent,
    validation_agent,
    runtime,
    llm_router,
    workspace_access,
)
live_conversation_runner = LiveConversationRunner(
    settings.openai_api_key,
    settings.openai_model,
    settings.openai_base_url,
    mcp_client,
)
conversation_agent = ConversationAgent(
    store,
    mock_system,
    live_conversation_runner,
)
openai_manager_loop = OpenAIManagerLoop(
    settings.openai_api_key,
    settings.openai_model,
    settings.openai_base_url,
)
agentic_manager = AgenticManager(
    store,
    architecture_agent,
    managed_workspace,
    openai_manager_loop,
)
