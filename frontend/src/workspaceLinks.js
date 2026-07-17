export function findWorkspaceTarget(result, architecture) {
  const agents = architecture?.agents || [];
  const tools = architecture?.tools || [];
  let tool = result.kind === "tool"
    ? tools.find((item) => item.id === result.id || item.name === result.name)
    : null;

  if (result.kind === "endpoint") {
    tool = tools.find((item) => item.endpoint_ids?.includes(result.id));
  }

  if (result.kind === "agent") {
    const agent = agents.find((item) => item.id === result.id || item.name === result.name);
    return agent ? { agentId: agent.id, agentName: agent.name, toolName: null } : null;
  }

  if (!tool) return null;

  const agent = agents.find((item) => (
    item.tool_ids?.includes(tool.id)
    || item.mcp_tools?.some((capability) => capability.name === tool.name)
    || item.name.toLowerCase() === tool.owner?.toLowerCase()
  ));

  return agent
    ? { agentId: agent.id, agentName: agent.name, toolName: tool.name }
    : null;
}

export function workspaceUrl({
  agentId,
  mode = "edit",
  toolName,
  conversationId,
  context,
} = {}) {
  const params = new URLSearchParams();
  if (agentId) params.set("agent", agentId);
  params.set("mode", mode);
  if (toolName) params.set("tool", toolName);
  if (conversationId) params.set("conversation", conversationId);
  if (context) params.set("context", context);
  return `/workspace?${params.toString()}`;
}
